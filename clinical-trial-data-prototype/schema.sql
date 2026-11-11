-- Clinical trial data prototype (SQLite)
-- Fictional trial: 5 scheduled visits per participant, 4 measurements per visit.
-- All data in this project is SYNTHETIC.


-- 1. CORE TABLES
-------------------------------------------------------------------

CREATE TABLE sites (
    site_id    INTEGER PRIMARY KEY,
    site_name  TEXT NOT NULL,
    city       TEXT NOT NULL
);

CREATE TABLE participants (
    participant_id TEXT PRIMARY KEY,                       -- e.g. P0001
    site_id        INTEGER NOT NULL REFERENCES sites(site_id),
    birth_date     TEXT,
    sex            TEXT CHECK (sex IN ('F', 'M')),
    status         TEXT NOT NULL DEFAULT 'Screening'
                   CHECK (status IN ('Screening','Consent','Enrolled','Active',
                                     'Completed','Withdrawn','Screen Failed')),
    enrolled_date  TEXT
);

CREATE TABLE visits (
    visit_id       INTEGER PRIMARY KEY,
    participant_id TEXT NOT NULL REFERENCES participants(participant_id),
    visit_number   INTEGER NOT NULL CHECK (visit_number BETWEEN 1 AND 5),
    scheduled_date TEXT NOT NULL,
    actual_date    TEXT,
    status         TEXT NOT NULL DEFAULT 'Scheduled'
                   CHECK (status IN ('Scheduled','Completed','Missed')),
    UNIQUE (participant_id, visit_number)                  -- one row per visit per person
);

-- One row per completed visit
-- A NULL value means "not entered".
CREATE TABLE measurements (
    measurement_id INTEGER PRIMARY KEY AUTOINCREMENT,
    visit_id       INTEGER NOT NULL UNIQUE REFERENCES visits(visit_id),
    systolic_bp    INTEGER,
    diastolic_bp   INTEGER,
    heart_rate     INTEGER,
    weight_kg      REAL
);


-- 2. CONFIGURATION TABLES
-------------------------------------------------------------------

CREATE TABLE reference_ranges (
    measurement TEXT PRIMARY KEY,
    min_value   INTEGER NOT NULL,
    max_value   INTEGER NOT NULL
);

INSERT INTO reference_ranges VALUES
    ('systolic_bp',  70, 200),
    ('diastolic_bp', 40, 120),
    ('heart_rate',   40, 150),
    ('weight_kg',    35, 200);

-- Which status changes are legal for a participant.
CREATE TABLE allowed_transitions (
    from_status TEXT NOT NULL,
    to_status   TEXT NOT NULL,
    PRIMARY KEY (from_status, to_status)
);

INSERT INTO allowed_transitions VALUES
    ('Screening', 'Consent'),
    ('Screening', 'Screen Failed'),
    ('Consent',   'Enrolled'),
    ('Consent',   'Withdrawn'),
    ('Enrolled',  'Active'),
    ('Enrolled',  'Withdrawn'),
    ('Active',    'Completed'),
    ('Active',    'Withdrawn');


-- 3. AUDIT TRAIL
-------------------------------------------------------------------

-- The app sets who is making changes and why BEFORE it edits data.
-- The triggers below read this row. (SQLite has no database users,
-- so this is how we know "who" and "why".)
CREATE TABLE session_context (
    id        INTEGER PRIMARY KEY CHECK (id = 1),
    user_name TEXT NOT NULL,
    reason    TEXT
);
INSERT INTO session_context VALUES (1, 'system', 'initial data load');

CREATE TABLE audit_log (
    audit_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id  TEXT NOT NULL,
    field_name TEXT NOT NULL,
    old_value  TEXT,
    new_value  TEXT,
    changed_by TEXT NOT NULL,
    reason     TEXT,
    changed_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Log every edit to a measurement value (only the fields that actually changed).
CREATE TRIGGER trg_audit_measurements_update
AFTER UPDATE ON measurements
BEGIN
    INSERT INTO audit_log (table_name, record_id, field_name, old_value, new_value, changed_by, reason)
    SELECT 'measurements', NEW.measurement_id, 'systolic_bp', OLD.systolic_bp, NEW.systolic_bp, user_name, reason
    FROM session_context WHERE id = 1 AND OLD.systolic_bp IS NOT NEW.systolic_bp;

    INSERT INTO audit_log (table_name, record_id, field_name, old_value, new_value, changed_by, reason)
    SELECT 'measurements', NEW.measurement_id, 'diastolic_bp', OLD.diastolic_bp, NEW.diastolic_bp, user_name, reason
    FROM session_context WHERE id = 1 AND OLD.diastolic_bp IS NOT NEW.diastolic_bp;

    INSERT INTO audit_log (table_name, record_id, field_name, old_value, new_value, changed_by, reason)
    SELECT 'measurements', NEW.measurement_id, 'heart_rate', OLD.heart_rate, NEW.heart_rate, user_name, reason
    FROM session_context WHERE id = 1 AND OLD.heart_rate IS NOT NEW.heart_rate;

    INSERT INTO audit_log (table_name, record_id, field_name, old_value, new_value, changed_by, reason)
    SELECT 'measurements', NEW.measurement_id, 'weight_kg', OLD.weight_kg, NEW.weight_kg, user_name, reason
    FROM session_context WHERE id = 1 AND OLD.weight_kg IS NOT NEW.weight_kg;
END;

-- Log deletions too (who removed a record is exactly what an auditor asks).
CREATE TRIGGER trg_audit_measurements_delete
AFTER DELETE ON measurements
BEGIN
    INSERT INTO audit_log (table_name, record_id, field_name, old_value, new_value, changed_by, reason)
    SELECT 'measurements', OLD.measurement_id, '(record deleted)', 'visit_id=' || OLD.visit_id, NULL, user_name, reason
    FROM session_context WHERE id = 1;
END;

-- Log participant status changes.
CREATE TRIGGER trg_audit_participant_status
AFTER UPDATE OF status ON participants
WHEN OLD.status <> NEW.status
BEGIN
    INSERT INTO audit_log (table_name, record_id, field_name, old_value, new_value, changed_by, reason)
    SELECT 'participants', NEW.participant_id, 'status', OLD.status, NEW.status, user_name, reason
    FROM session_context WHERE id = 1;
END;

-- Make the audit log append-only: nobody can edit or delete history.
CREATE TRIGGER trg_audit_no_update
BEFORE UPDATE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: edits are not allowed');
END;

CREATE TRIGGER trg_audit_no_delete
BEFORE DELETE ON audit_log
BEGIN
    SELECT RAISE(ABORT, 'audit_log is append-only: deletes are not allowed');
END;

-------------------------------------------------------------------
-- 4. WORKFLOW RULE: block illegal participant status changes
-------------------------------------------------------------------

CREATE TRIGGER trg_status_transition
BEFORE UPDATE OF status ON participants
WHEN OLD.status <> NEW.status
 AND NOT EXISTS (SELECT 1 FROM allowed_transitions
                 WHERE from_status = OLD.status AND to_status = NEW.status)
BEGIN
    SELECT RAISE(ABORT, 'Invalid status change: not allowed by the study workflow');
END;
