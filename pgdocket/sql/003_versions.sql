-- pgdocket ledger, version 003: comparing versions before promoting one (ADR 0002, issue #15).
--
-- * Probe judgments: a re-ask of a row under a version, recorded in the ledger but never made the live answer.
--   Comparing a new version against an old one needs the old one's own run-to-run noise as a baseline.
-- * The queue is keyed by purpose, so a queued probe never makes a row look pending.
-- * Versions keep the comparison that justified them and when they were promoted.

ALTER TABLE docket.judgment ADD COLUMN purpose text NOT NULL DEFAULT 'live' CHECK (purpose IN ('live', 'probe'));

ALTER TABLE docket.queue ADD COLUMN purpose text NOT NULL DEFAULT 'live' CHECK (purpose IN ('live', 'probe'));
ALTER TABLE docket.queue DROP CONSTRAINT queue_pkey;
ALTER TABLE docket.queue ADD PRIMARY KEY (decision_id, version, row_key, purpose);

ALTER TABLE docket.version ADD COLUMN comparison jsonb;          -- set by `pgdocket compare`
ALTER TABLE docket.version ADD COLUMN promoted_at timestamptz;

-- ------------------------------------------------------------------ queueing: same as 001, keyed by purpose
CREATE OR REPLACE FUNCTION docket.enqueue() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
DECLARE
    k text := to_jsonb(NEW) ->> TG_ARGV[1];
BEGIN
    INSERT INTO docket.queue (decision_id, version, row_key)
    SELECT v.decision_id, v.version, k
    FROM docket.version v
    WHERE v.decision_id = TG_ARGV[0]::bigint AND v.status <> 'retired'
    ON CONFLICT (decision_id, version, row_key, purpose) DO UPDATE
        SET enqueued_at = now(), attempts = 0, locked_until = NULL, claim = NULL, last_error = NULL;
    PERFORM pg_notify('docket', TG_ARGV[0]);
    RETURN NULL;
END $$;

CREATE OR REPLACE FUNCTION docket.backfill(p_name text, p_version int DEFAULT NULL) RETURNS bigint
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
         ON CONFLICT (decision_id, version, row_key, purpose) DO NOTHING', d.id, ver, d.key_column, d.source);
    GET DIAGNOSTICS n = ROW_COUNT;
    PERFORM pg_notify('docket', d.id::text);
    RETURN n;
END $$;

-- ------------------------------------------------------------------ the per-decision view, now in one place
CREATE OR REPLACE FUNCTION docket.create_view(p_decision bigint) RETURNS void
LANGUAGE plpgsql AS $$
DECLARE
    d docket.decision;
BEGIN
    SELECT * INTO d FROM docket.decision WHERE id = p_decision;
    EXECUTE format($v$
        CREATE OR REPLACE VIEW docket.%I AS
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
                                AND q.purpose = 'live'
        LEFT JOIN LATERAL (SELECT docket.calibrated(j.answer, v.spec, v.calibration) AS conf) cal ON true
        WHERE d.id = %s
    $v$, 'v_' || d.name, d.key_column, d.source, d.key_column, d.key_column, d.id);
END $$;

CREATE OR REPLACE FUNCTION docket.create_decision(
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
    INSERT INTO docket.version (decision_id, version, spec, spec_hash, status, promoted_at)
    VALUES (d, 1, p_spec, md5(p_spec::text), 'active', now());

    SELECT string_agg(format('OLD.%1$I IS DISTINCT FROM NEW.%1$I', t), ' OR ') INTO changed FROM unnest(p_text) t;
    EXECUTE format('CREATE TRIGGER %I AFTER INSERT ON %s FOR EACH ROW EXECUTE FUNCTION docket.enqueue(%L, %L)',
                   'docket_' || p_name || '_ins', src, d, p_key);
    EXECUTE format('CREATE TRIGGER %I AFTER UPDATE ON %s FOR EACH ROW WHEN (%s) EXECUTE FUNCTION docket.enqueue(%L, %L)',
                   'docket_' || p_name || '_upd', src, changed, d, p_key);
    PERFORM docket.create_view(d);

    IF p_backfill THEN
        PERFORM docket.backfill(p_name);
    END IF;
    RETURN d;
END $$;

-- Existing decisions get the new view (it ignores queued probes).
SELECT docket.create_view(id) FROM docket.decision;
UPDATE docket.version v SET promoted_at = v.created_at WHERE v.status = 'active' AND v.promoted_at IS NULL;

-- ------------------------------------------------------------------ comparing a shadow version with the active one
-- Queue `p_n` rows already judged by the active version: each is judged by the shadow version (live for that
-- version) and re-asked by the active version as a probe (its noise baseline). Rows with random-sample labels
-- come first, so accuracy can be compared on them; the rest are a seeded random sample. Returns rows chosen.
CREATE OR REPLACE FUNCTION docket.compare_enqueue(p_name text, p_version int, p_n int, p_seed text DEFAULT '1')
RETURNS int
LANGUAGE plpgsql AS $$
DECLARE
    d docket.decision;
    n int;
BEGIN
    SELECT * INTO d FROM docket.decision WHERE name = p_name;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'docket: no decision named %', p_name;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM docket.version WHERE decision_id = d.id AND version = p_version AND status = 'shadow') THEN
        RAISE EXCEPTION 'docket: % has no shadow version %', p_name, p_version;
    END IF;
    WITH sample AS (
        SELECT c.row_key
        FROM docket.current c
        LEFT JOIN docket.label l ON l.decision_id = c.decision_id AND l.row_key = c.row_key AND l.sampling = 'random'
        WHERE c.decision_id = d.id AND c.version = d.active_version
        ORDER BY (l.row_key IS NOT NULL) DESC, md5(c.row_key || ':' || p_seed)
        LIMIT p_n
    ), queued AS (
        INSERT INTO docket.queue (decision_id, version, row_key, purpose)
        SELECT d.id, p_version, row_key, 'live' FROM sample
        UNION ALL
        SELECT d.id, d.active_version, row_key, 'probe' FROM sample
        ON CONFLICT (decision_id, version, row_key, purpose) DO NOTHING
        RETURNING 1
    )
    SELECT (SELECT count(*) FROM sample) INTO n;
    PERFORM pg_notify('docket', d.id::text);
    RETURN n;
END $$;

CREATE OR REPLACE FUNCTION docket.promote(p_name text, p_version int) RETURNS void
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
    UPDATE docket.version SET status = 'active', promoted_at = now() WHERE decision_id = d.id AND version = p_version;
    UPDATE docket.decision SET active_version = p_version WHERE id = d.id;
    DELETE FROM docket.queue WHERE decision_id = d.id AND version = d.active_version;
END $$;

-- Stand down a shadow version that won't be promoted: it stops judging new and changed rows. Its judgments
-- stay in the ledger.
CREATE OR REPLACE FUNCTION docket.retire(p_name text, p_version int) RETURNS void
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
    UPDATE docket.version SET status = 'retired' WHERE decision_id = d.id AND version = p_version;
    DELETE FROM docket.queue WHERE decision_id = d.id AND version = p_version;
END $$;

-- Health at a glance, with queued probes and shadow versions.
CREATE OR REPLACE VIEW docket.status AS
SELECT d.name, d.source, d.active_version AS version,
       (SELECT count(*) FROM docket.current c WHERE c.decision_id = d.id AND c.version = d.active_version) AS judged,
       (SELECT count(*) FROM docket.queue q WHERE q.decision_id = d.id AND q.attempts < 5 AND q.purpose = 'live') AS queued,
       (SELECT count(*) FROM docket.queue q WHERE q.decision_id = d.id AND q.attempts >= 5) AS errors,
       (SELECT count(*) FROM docket.label l WHERE l.decision_id = d.id) AS labels,
       (SELECT coalesce(sum(tokens), 0) FROM docket.judgment j WHERE j.decision_id = d.id) AS tokens,
       (v.calibration IS NOT NULL) AS calibrated,
       (SELECT count(*) FROM docket.queue q WHERE q.decision_id = d.id AND q.attempts < 5 AND q.purpose = 'probe') AS probes_queued,
       (SELECT count(*) FROM docket.version s WHERE s.decision_id = d.id AND s.status = 'shadow') AS shadow_versions
FROM docket.decision d
JOIN docket.version v ON v.decision_id = d.id AND v.version = d.active_version;
