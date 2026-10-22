-- docket migration 005 (#19): one guaranteed threshold per answer.
-- `pgdocket calibrate --per-answer` stores `thresholds` (answer -> threshold on judgment.score, or null when that
-- answer's labelled rows can't certify the target). The view then accepts a row when its own answer's threshold is
-- met; answers without one are never `auto`. Calibrations without `thresholds` keep the rules of migration 004.

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
                    THEN CASE WHEN CASE WHEN v.calibration->>'threshold' IS NULL THEN cal.conf >= 0.5
                                        WHEN v.calibration->>'threshold_on' = 'raw score'
                                        THEN j.score >= (v.calibration->>'threshold')::float8
                                        ELSE cal.conf >= (v.calibration->>'threshold')::float8 END
                              THEN 'yes' ELSE 'no' END
                    ELSE j.value END AS answer,
               j.score AS raw_score,
               cal.conf AS confidence,
               CASE WHEN v.calibration IS NULL OR j.id IS NULL THEN NULL
                    WHEN v.calibration ? 'thresholds'
                    THEN coalesce(j.score >= (v.calibration->'thresholds'->>j.value)::float8, false)
                    WHEN v.calibration->>'threshold' IS NULL THEN false
                    WHEN v.calibration->>'threshold_on' = 'raw score' THEN j.score >= (v.calibration->>'threshold')::float8
                    ELSE cal.conf >= (v.calibration->>'threshold')::float8 END AS auto,
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

SELECT docket.create_view(id) FROM docket.decision;
