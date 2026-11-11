-- Validation checks. Every query returns the same 5 columns:
--   check_name, site_id, participant_id, visit_id, detail
-- run_checks.py runs each one ("-- name:" marks the start of a query).

-- name: missing_required
-- A completed visit must have all 4 measurements.
SELECT
    'missing_required' AS check_name,
    p.site_id          AS site_id,
    v.participant_id   AS participant_id,
    v.visit_id         AS visit_id,
    CASE
        WHEN m.visit_id IS NULL THEN 'no measurement record'
        ELSE 'missing: ' || TRIM(
            (CASE WHEN m.systolic_bp  IS NULL THEN 'systolic_bp '  ELSE '' END) ||
            (CASE WHEN m.diastolic_bp IS NULL THEN 'diastolic_bp ' ELSE '' END) ||
            (CASE WHEN m.heart_rate   IS NULL THEN 'heart_rate '   ELSE '' END) ||
            (CASE WHEN m.weight_kg    IS NULL THEN 'weight_kg '    ELSE '' END))
    END AS detail
FROM visits v
JOIN participants p ON p.participant_id = v.participant_id
LEFT JOIN measurements m ON m.visit_id = v.visit_id
WHERE v.status = 'Completed'
  AND (m.visit_id IS NULL
       OR m.systolic_bp IS NULL OR m.diastolic_bp IS NULL
       OR m.heart_rate IS NULL OR m.weight_kg IS NULL);

-- name: out_of_range
-- Values outside the limits in the reference_ranges table.
-- The CTE turns the 4 measurement columns into rows so one join checks them all.
WITH long_format AS (
    SELECT visit_id, 'systolic_bp'  AS measurement, systolic_bp  AS value FROM measurements
    UNION ALL
    SELECT visit_id, 'diastolic_bp', diastolic_bp FROM measurements
    UNION ALL
    SELECT visit_id, 'heart_rate',   heart_rate   FROM measurements
    UNION ALL
    SELECT visit_id, 'weight_kg',    weight_kg    FROM measurements
)
SELECT
    'out_of_range'   AS check_name,
    p.site_id        AS site_id,
    v.participant_id AS participant_id,
    v.visit_id       AS visit_id,
    l.measurement || ' = ' || l.value ||
        ' (allowed ' || r.min_value || ' to ' || r.max_value || ')' AS detail
FROM long_format l
JOIN reference_ranges r ON r.measurement = l.measurement
JOIN visits v ON v.visit_id = l.visit_id
JOIN participants p ON p.participant_id = v.participant_id
WHERE l.value IS NOT NULL
  AND (l.value < r.min_value OR l.value > r.max_value);

-- name: diastolic_ge_systolic
-- Diastolic (bottom number) can never be equal to or higher than systolic (top number).
SELECT
    'diastolic_ge_systolic' AS check_name,
    p.site_id               AS site_id,
    v.participant_id        AS participant_id,
    v.visit_id              AS visit_id,
    'BP entered as ' || m.systolic_bp || '/' || m.diastolic_bp AS detail
FROM measurements m
JOIN visits v ON v.visit_id = m.visit_id
JOIN participants p ON p.participant_id = v.participant_id
WHERE m.diastolic_bp >= m.systolic_bp;

-- name: out_of_window
-- Protocol rule: a visit must happen within 3 days of its scheduled date.
SELECT
    'out_of_window'  AS check_name,
    p.site_id        AS site_id,
    v.participant_id AS participant_id,
    v.visit_id       AS visit_id,
    'visit ' || v.visit_number || ' happened ' ||
        CAST(ABS(julianday(v.actual_date) - julianday(v.scheduled_date)) AS INTEGER) ||
        ' days from its scheduled date (window is 3)' AS detail
FROM visits v
JOIN participants p ON p.participant_id = v.participant_id
WHERE v.status = 'Completed'
  AND v.actual_date IS NOT NULL
  AND ABS(julianday(v.actual_date) - julianday(v.scheduled_date)) > 3;

-- name: duplicate_participant
-- Same person registered twice under different IDs.
SELECT
    'duplicate_participant'          AS check_name,
    site_id                          AS site_id,
    group_concat(participant_id, ' / ') AS participant_id,
    NULL                             AS visit_id,
    'same site, birth date, sex and enrollment date' AS detail
FROM participants
GROUP BY site_id, birth_date, sex, enrolled_date
HAVING COUNT(*) > 1;

-- name: status_mismatch
-- Participant is marked Completed but did not finish all 5 visits.
SELECT
    'status_mismatch' AS check_name,
    p.site_id         AS site_id,
    p.participant_id  AS participant_id,
    NULL              AS visit_id,
    'status is Completed but only ' ||
        COUNT(CASE WHEN v.status = 'Completed' THEN 1 END) || ' of 5 visits completed' AS detail
FROM participants p
JOIN visits v ON v.participant_id = p.participant_id
WHERE p.status = 'Completed'
GROUP BY p.participant_id
HAVING COUNT(CASE WHEN v.status = 'Completed' THEN 1 END) < 5;
