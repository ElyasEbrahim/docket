-- pgdocket ledger, version 002: counts with error bars (prediction-powered inference, PPI++).
-- Same formulas as pgdocket/estimate.py; integration tests check that both agree.

-- How each label was chosen. Only a uniform random sample gives valid intervals (ADR 0003):
--   random  a random sample (pgdocket label --sample N, or a CSV marked --random)
--   all     every row that had a value in the label column (not a random sample of the population)
--   manual  chosen by hand (CSV); never used for estimates unless asked
ALTER TABLE docket.label ADD COLUMN sampling text NOT NULL DEFAULT 'manual'
    CHECK (sampling IN ('random', 'all', 'manual'));

-- Inverse standard normal CDF (Acklam's approximation, relative error < 1.2e-9), as in pgdocket.estimate.norm_ppf.
CREATE OR REPLACE FUNCTION docket.norm_ppf(p float8) RETURNS float8
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
    a float8[] := ARRAY[-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
                         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00];
    b float8[] := ARRAY[-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
                         6.680131188771972e+01, -1.328068155288572e+01];
    c float8[] := ARRAY[-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
                        -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00];
    d float8[] := ARRAY[7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
                        3.754408661907416e+00];
    q float8;
    r float8;
BEGIN
    IF p <= 0 OR p >= 1 THEN
        RAISE EXCEPTION 'docket.norm_ppf: p must be in (0, 1)';
    END IF;
    IF p < 0.02425 THEN
        q := sqrt(-2 * ln(p));
        RETURN (((((c[1] * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) * q + c[6]) /
               ((((d[1] * q + d[2]) * q + d[3]) * q + d[4]) * q + 1);
    END IF;
    IF p > 1 - 0.02425 THEN
        RETURN -docket.norm_ppf(1 - p);
    END IF;
    q := p - 0.5;
    r := q * q;
    RETURN (((((a[1] * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * r + a[6]) * q /
           (((((b[1] * r + b[2]) * r + b[3]) * r + b[4]) * r + b[5]) * r + 1);
END $$;

-- How many judged rows (in an optional scope) truly have answer X, with a confidence interval.
--   p_answer   one option (choice) or 'yes' (yes/no); NULL = every option
--   p_where    SQL condition on the source table, e.g. $$created_at >= '2026-07-01'$$
--   p_level    confidence level of the intervals
--   p_sampling which labels may be used; only random samples give valid intervals
CREATE OR REPLACE FUNCTION docket.estimate(
    p_name text, p_answer text DEFAULT NULL, p_where text DEFAULT NULL, p_level float8 DEFAULT 0.95,
    p_sampling text[] DEFAULT ARRAY['random']
) RETURNS TABLE (
    answer text, rows_in_scope bigint, judged bigint, labels bigint, labels_with bigint,
    model_count float8, estimate float8, ci_low float8, ci_high float8,
    labels_only_low float8, labels_only_high float8, lambda float8, reliable boolean, note text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
    d       docket.decision;
    spec    jsonb;
    answers text[];
    ans     text;
    z       float8 := docket.norm_ppf(0.5 + p_level / 2);
    cond    text := CASE WHEN p_where IS NULL OR btrim(p_where) = '' THEN 'true' ELSE p_where END;
    s       record;
    lam     float8;
    theta   float8;
    se      float8;
    se_l    float8;
    n_tot   float8;
BEGIN
    SELECT * INTO d FROM docket.decision WHERE name = p_name;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'docket: no decision named %', p_name;
    END IF;
    SELECT v.spec INTO spec FROM docket.version v WHERE v.decision_id = d.id AND v.version = d.active_version;
    IF p_answer IS NOT NULL THEN
        answers := ARRAY[p_answer];
    ELSIF spec->>'kind' = 'noul' THEN
        answers := ARRAY['yes'];
    ELSE
        SELECT array_agg(o->>'name' ORDER BY ord) INTO answers FROM jsonb_array_elements(spec->'options') WITH ORDINALITY AS t(o, ord);
    END IF;

    FOREACH ans IN ARRAY answers LOOP
        -- One pass over the scope: f = the model said `ans` (0/1); y = the label says `ans` (0/1, labelled rows only).
        EXECUTE format($q$
            WITH scope AS (
                SELECT v.status, v.answer, s.%1$I::text AS k
                FROM %2$s s JOIN docket.%3$I v ON v.key = s.%1$I
                WHERE %4$s
            ), rows AS (
                SELECT sc.status, (sc.answer = %5$L)::int AS f, l.label IS NOT NULL AS labelled, (l.label = %5$L)::int AS y
                FROM scope sc
                LEFT JOIN docket.label l ON l.decision_id = %6$s AND l.row_key = sc.k AND l.sampling = ANY(%7$L::text[])
            )
            SELECT count(*) AS in_scope,
                   count(*) FILTER (WHERE status = 'judged') AS judged,
                   count(*) FILTER (WHERE status = 'judged' AND labelled) AS n,
                   count(*) FILTER (WHERE status = 'judged' AND NOT labelled) AS nu,
                   coalesce(sum(y) FILTER (WHERE status = 'judged' AND labelled), 0) AS k,
                   avg(f) FILTER (WHERE status = 'judged') AS f_all,
                   var_samp(f) FILTER (WHERE status = 'judged') AS var_f,
                   avg(f) FILTER (WHERE status = 'judged' AND NOT labelled) AS fu,
                   var_samp(f) FILTER (WHERE status = 'judged' AND NOT labelled) AS var_fu,
                   avg(f) FILTER (WHERE status = 'judged' AND labelled) AS fl,
                   var_samp(f) FILTER (WHERE status = 'judged' AND labelled) AS var_fl,
                   avg(y) FILTER (WHERE status = 'judged' AND labelled) AS ybar,
                   var_samp(y) FILTER (WHERE status = 'judged' AND labelled) AS var_y,
                   covar_samp(y, f) FILTER (WHERE status = 'judged' AND labelled) AS cov_yf
            FROM rows
        $q$, d.key_column, d.source, 'v_' || p_name, cond, ans, d.id, p_sampling) INTO s;

        answer := ans; rows_in_scope := s.in_scope; judged := s.judged; labels := s.n; labels_with := s.k;
        model_count := coalesce(s.f_all, 0) * s.judged;
        estimate := NULL; ci_low := NULL; ci_high := NULL; labels_only_low := NULL; labels_only_high := NULL;
        lambda := NULL; reliable := false; note := NULL;
        n_tot := s.judged;

        IF s.n < 2 THEN
            note := 'no random-sample labels in scope: import some with pgdocket label --sample N';
        ELSIF s.k = 0 OR s.k = s.n THEN
            note := format('no labelled rows %s this answer among %s: cannot estimate; label more rows',
                           CASE WHEN s.k = 0 THEN 'with' ELSE 'without' END, s.n);
        ELSE
            se_l := sqrt(s.var_y / s.n);
            labels_only_low := greatest(0, s.ybar - z * se_l) * n_tot;
            labels_only_high := least(1, s.ybar + z * se_l) * n_tot;
            IF s.nu < 2 THEN
                lam := 0; theta := s.ybar; se := se_l;
            ELSE
                lam := CASE WHEN coalesce(s.var_f, 0) <= 0 THEN 0
                            ELSE least(1, greatest(0, s.cov_yf / ((1 + s.n::float8 / s.nu) * s.var_f))) END;
                theta := s.ybar + lam * (s.fu - s.fl);
                se := sqrt(greatest(0, (s.var_y + lam * lam * s.var_fl - 2 * lam * s.cov_yf) / s.n
                                        + lam * lam * s.var_fu / s.nu));
            END IF;
            estimate := theta * n_tot;
            ci_low := greatest(0, theta - z * se) * n_tot;
            ci_high := least(1, theta + z * se) * n_tot;
            lambda := lam;
            reliable := least(s.k, s.n - s.k) >= 10;
            IF NOT reliable THEN
                note := format('only %s labelled rows with and %s without this answer; the interval may be too narrow (need 10 each)',
                               s.k, s.n - s.k);
            END IF;
        END IF;
        IF s.in_scope > s.judged THEN
            note := concat_ws('; ', note, format('%s rows in scope are not judged yet and are not counted', s.in_scope - s.judged));
        END IF;
        RETURN NEXT;
    END LOOP;
END $$;
