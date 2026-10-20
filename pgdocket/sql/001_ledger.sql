-- pgdocket ledger, version 001. Plain SQL + PL/pgSQL: no superuser, no extensions (ADR 0001, 0004).
-- Applied by `python -m docket install`, which records it in docket.migration.

CREATE SCHEMA IF NOT EXISTS docket;

CREATE TABLE docket.decision (
    id             bigserial PRIMARY KEY,
    name           text NOT NULL UNIQUE CHECK (name ~ '^[a-z][a-z0-9_]{0,40}$'),
    source         text NOT NULL,               -- quoted schema.table
    key_column     text NOT NULL,
    key_type       text NOT NULL,               -- format_type() of the key column
    text_columns   text[] NOT NULL,
    active_version int,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE docket.version (
    decision_id  bigint NOT NULL REFERENCES docket.decision ON DELETE CASCADE,
    version      int NOT NULL,
    spec         jsonb NOT NULL,                -- kind, question, options, backend, model, batch_size
    spec_hash    text NOT NULL,
    status       text NOT NULL CHECK (status IN ('shadow', 'active', 'retired')),
    calibration  jsonb,                         -- set by `docket calibrate`
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (decision_id, version)
);

-- Append-only ledger: every answer ever given, never updated.
CREATE TABLE docket.judgment (
    id           bigserial PRIMARY KEY,
    decision_id  bigint NOT NULL,
    version      int NOT NULL,
    row_key      text NOT NULL,
    input_hash   text NOT NULL,                 -- md5 of the exact JSON sent to the backend
    answer       jsonb NOT NULL,                -- raw backend answer
    value        text,                          -- choice: option name; noul: NULL
    score        float8 NOT NULL,               -- choice: probability of that option; noul: probability of yes (raw)
    tokens       int,
    judged_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (decision_id, version) REFERENCES docket.version ON DELETE CASCADE
);
CREATE INDEX judgment_by_row ON docket.judgment (decision_id, version, row_key, id DESC);

-- Latest judgment per row and version: a cache of the ledger, so reads are one primary-key join.
CREATE TABLE docket.current (
    decision_id  bigint NOT NULL,
    version      int NOT NULL,
    row_key      text NOT NULL,
    judgment_id  bigint NOT NULL REFERENCES docket.judgment ON DELETE CASCADE,
    PRIMARY KEY (decision_id, version, row_key)
);

CREATE TABLE docket.queue (
    decision_id  bigint NOT NULL,
    version      int NOT NULL,
    row_key      text NOT NULL,
    enqueued_at  timestamptz NOT NULL DEFAULT now(),
    attempts     int NOT NULL DEFAULT 0,
    locked_until timestamptz,
    claim        uuid,
    last_error   text,
    PRIMARY KEY (decision_id, version, row_key),
    FOREIGN KEY (decision_id, version) REFERENCES docket.version ON DELETE CASCADE
);
CREATE INDEX queue_ready ON docket.queue (enqueued_at) WHERE attempts < 5;

-- Human labels used for calibration.
CREATE TABLE docket.label (
    decision_id  bigint NOT NULL REFERENCES docket.decision ON DELETE CASCADE,
    row_key      text NOT NULL,
    label        text NOT NULL,
    source       text,
    labeled_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (decision_id, row_key)
);

-- ------------------------------------------------------------------ trigger: enqueue changed rows
-- SECURITY DEFINER so that roles writing to the source table need no grant on the docket schema;
-- search_path is pinned so the function can't be redirected.
CREATE FUNCTION docket.enqueue() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    k text := to_jsonb(NEW) ->> TG_ARGV[1];
BEGIN
    INSERT INTO docket.queue (decision_id, version, row_key)
    SELECT v.decision_id, v.version, k
    FROM docket.version v
    WHERE v.decision_id = TG_ARGV[0]::bigint AND v.status <> 'retired'
    ON CONFLICT (decision_id, version, row_key) DO UPDATE
        SET enqueued_at = now(), attempts = 0, locked_until = NULL, claim = NULL, last_error = NULL;
    PERFORM pg_notify('docket', TG_ARGV[0]);
    RETURN NULL;
END $$;

-- ------------------------------------------------------------------ calibration, applied at read time
-- choice: clamp zeros at `floor`, then temperature T: top^(1/T) / sum(p^(1/T)) (row normalisation cancels out).
-- noul:   Platt scaling sigmoid(a * logit(p) + b).
-- Without a calibration: the raw top-option probability (choice) or yes-probability (noul).
CREATE FUNCTION docket.calibrated(answer jsonb, spec jsonb, cal jsonb) RETURNS float8
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE
    p   float8;
    t   float8;
    f   float8;
    num float8;
    den float8;
BEGIN
    IF answer IS NULL THEN
        RETURN NULL;
    END IF;
    IF spec->>'kind' = 'noul' THEN
        p := (answer->>'noul')::float8;
        IF cal IS NULL THEN
            RETURN p;
        END IF;
        p := least(greatest(p, 1e-6), 1 - 1e-6);
        RETURN 1 / (1 + exp(-((cal->>'a')::float8 * ln(p / (1 - p)) + (cal->>'b')::float8)));
    END IF;
    IF cal IS NULL THEN
        RETURN (SELECT max(value::float8) FROM jsonb_each_text(answer->'probabilities'));
    END IF;
    t := (cal->>'temperature')::float8;
    f := coalesce((cal->>'floor')::float8, 0);
    SELECT max(greatest(value::float8, f)), sum(power(greatest(value::float8, f), 1 / t))
      INTO num, den
      FROM jsonb_each_text(answer->'probabilities');
    RETURN power(num, 1 / t) / den;
END $$;

-- ------------------------------------------------------------------ decisions
CREATE FUNCTION docket.backfill(p_name text, p_version int DEFAULT NULL) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
    d   docket.decision;
    ver int;
    n   bigint;
BEGIN
    SELECT * INTO d FROM docket.decision WHERE name = p_name;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'docket: no decision named %', p_name;
    END IF;
    ver := coalesce(p_version, d.active_version);
    EXECUTE format(
        'INSERT INTO docket.queue (decision_id, version, row_key)
         SELECT %s, %s, s.%I::text FROM %s s
         ON CONFLICT (decision_id, version, row_key) DO NOTHING', d.id, ver, d.key_column, d.source);
    GET DIAGNOSTICS n = ROW_COUNT;
    PERFORM pg_notify('docket', d.id::text);
    RETURN n;
END $$;

CREATE FUNCTION docket.create_decision(
    p_name text, p_source regclass, p_key text, p_text text[], p_spec jsonb, p_backfill boolean DEFAULT true
) RETURNS bigint
LANGUAGE plpgsql AS $$
DECLARE
    d       bigint;
    src     text;
    ktype   text;
    missing text;
    changed text;
BEGIN
    IF p_name IN ('decision', 'version', 'judgment', 'current', 'queue', 'label', 'migration') THEN
        RAISE EXCEPTION 'docket: % is a reserved name', p_name;
    END IF;
    IF p_spec->>'kind' NOT IN ('choice', 'noul') THEN
        RAISE EXCEPTION 'docket: spec.kind must be choice or noul';
    END IF;
    IF coalesce(p_spec->>'question', '') = '' THEN
        RAISE EXCEPTION 'docket: spec.question is required';
    END IF;
    IF p_spec->>'kind' = 'choice' AND jsonb_array_length(coalesce(p_spec->'options', '[]')) < 2 THEN
        RAISE EXCEPTION 'docket: a choice needs at least two options';
    END IF;
    SELECT format('%I.%I', n.nspname, c.relname) INTO src
      FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace WHERE c.oid = p_source;
    SELECT format_type(a.atttypid, a.atttypmod) INTO ktype
      FROM pg_attribute a WHERE a.attrelid = p_source AND a.attname = p_key AND NOT a.attisdropped;
    IF ktype IS NULL THEN
        RAISE EXCEPTION 'docket: % has no column %', src, p_key;
    END IF;
    SELECT string_agg(t, ', ') INTO missing FROM unnest(p_text) t
     WHERE NOT EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = p_source AND a.attname = t AND NOT a.attisdropped);
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'docket: % has no column(s) %', src, missing;
    END IF;

    INSERT INTO docket.decision (name, source, key_column, key_type, text_columns, active_version)
    VALUES (p_name, src, p_key, ktype, p_text, 1) RETURNING id INTO d;
    INSERT INTO docket.version (decision_id, version, spec, spec_hash, status)
    VALUES (d, 1, p_spec, md5(p_spec::text), 'active');

    SELECT string_agg(format('OLD.%1$I IS DISTINCT FROM NEW.%1$I', t), ' OR ') INTO changed FROM unnest(p_text) t;
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT ON %s FOR EACH ROW EXECUTE FUNCTION docket.enqueue(%L, %L)',
                   'docket_' || p_name || '_ins', src, d, p_key);
    EXECUTE format('CREATE TRIGGER %I AFTER UPDATE ON %s FOR EACH ROW WHEN (%s) EXECUTE FUNCTION docket.enqueue(%L, %L)',
                   'docket_' || p_name || '_upd', src, changed, d, p_key);

    EXECUTE format($v$
        CREATE VIEW docket.%I AS
        SELECT s.%I AS key,
               CASE WHEN q.attempts >= 5 AND q.last_error IS NOT NULL THEN 'error'
                    WHEN q.row_key IS NOT NULL THEN 'pending'
                    WHEN j.id IS NULL THEN 'missing'
                    ELSE 'judged' END AS status,
               CASE WHEN v.spec->>'kind' = 'noul'
                    THEN CASE WHEN cal.conf >= coalesce((v.calibration->>'threshold')::float8, 0.5) THEN 'yes' ELSE 'no' END
                    ELSE j.value END AS answer,
               j.score AS raw_score,
               cal.conf AS confidence,
               cal.conf >= (v.calibration->>'threshold')::float8 AS auto,
               j.judged_at,
               c.version
        FROM %s s
        CROSS JOIN docket.decision d
        JOIN docket.version v ON v.decision_id = d.id AND v.version = d.active_version
        LEFT JOIN docket.current c ON c.decision_id = d.id AND c.version = d.active_version AND c.row_key = s.%I::text
        LEFT JOIN docket.judgment j ON j.id = c.judgment_id
        LEFT JOIN docket.queue q ON q.decision_id = d.id AND q.version = d.active_version AND q.row_key = s.%I::text
        LEFT JOIN LATERAL (SELECT docket.calibrated(j.answer, v.spec, v.calibration) AS conf) cal ON true
        WHERE d.id = %s
    $v$, 'v_' || p_name, p_key, src, p_key, p_key, d);

    IF p_backfill THEN
        PERFORM docket.backfill(p_name);
    END IF;
    RETURN d;
END $$;

-- A new version of a decision (e.g. a changed question or label set). It starts as 'shadow' and is judged for
-- every row alongside the active one; `docket.promote` makes it active.
CREATE FUNCTION docket.revise(p_name text, p_spec jsonb, p_backfill boolean DEFAULT true) RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    d   docket.decision;
    ver int;
BEGIN
    SELECT * INTO d FROM docket.decision WHERE name = p_name;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'docket: no decision named %', p_name;
    END IF;
    IF EXISTS (SELECT 1 FROM docket.version WHERE decision_id = d.id AND spec_hash = md5(p_spec::text) AND status <> 'retired') THEN
        RAISE EXCEPTION 'docket: an identical spec is already a live version of %', p_name;
    END IF;
    SELECT max(version) + 1 INTO ver FROM docket.version WHERE decision_id = d.id;
    INSERT INTO docket.version (decision_id, version, spec, spec_hash, status)
    VALUES (d.id, ver, p_spec, md5(p_spec::text), 'shadow');
    IF p_backfill THEN
        PERFORM docket.backfill(p_name, ver);
    END IF;
    RETURN ver;
END $$;

CREATE FUNCTION docket.promote(p_name text, p_version int) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    d docket.decision;
BEGIN
    SELECT * INTO d FROM docket.decision WHERE name = p_name;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'docket: no decision named %', p_name;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM docket.version WHERE decision_id = d.id AND version = p_version AND status = 'shadow') THEN
        RAISE EXCEPTION 'docket: % has no shadow version %', p_name, p_version;
    END IF;
    UPDATE docket.version SET status = 'retired' WHERE decision_id = d.id AND version = d.active_version;
    UPDATE docket.version SET status = 'active' WHERE decision_id = d.id AND version = p_version;
    UPDATE docket.decision SET active_version = p_version WHERE id = d.id;
    DELETE FROM docket.queue WHERE decision_id = d.id AND version = d.active_version;
END $$;

-- Remove a decision: its triggers, view, versions, ledger, queue and labels. The source table is untouched.
CREATE FUNCTION docket.drop_decision(p_name text) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    d docket.decision;
BEGIN
    SELECT * INTO d FROM docket.decision WHERE name = p_name;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'docket: no decision named %', p_name;
    END IF;
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %s', 'docket_' || p_name || '_ins', d.source);
    EXECUTE format('DROP TRIGGER IF EXISTS %I ON %s', 'docket_' || p_name || '_upd', d.source);
    EXECUTE format('DROP VIEW IF EXISTS docket.%I', 'v_' || p_name);
    DELETE FROM docket.current WHERE decision_id = d.id;
    DELETE FROM docket.queue WHERE decision_id = d.id;
    DELETE FROM docket.judgment WHERE decision_id = d.id;
    DELETE FROM docket.decision WHERE id = d.id;              -- cascades to versions and labels
END $$;

-- Health at a glance.
CREATE VIEW docket.status AS
SELECT d.name, d.source, d.active_version AS version,
       (SELECT count(*) FROM docket.current c WHERE c.decision_id = d.id AND c.version = d.active_version) AS judged,
       (SELECT count(*) FROM docket.queue q WHERE q.decision_id = d.id AND q.attempts < 5) AS queued,
       (SELECT count(*) FROM docket.queue q WHERE q.decision_id = d.id AND q.attempts >= 5) AS errors,
       (SELECT count(*) FROM docket.label l WHERE l.decision_id = d.id) AS labels,
       (SELECT coalesce(sum(tokens), 0) FROM docket.judgment j WHERE j.decision_id = d.id) AS tokens,
       (v.calibration IS NOT NULL) AS calibrated
FROM docket.decision d
JOIN docket.version v ON v.decision_id = d.id AND v.version = d.active_version;
