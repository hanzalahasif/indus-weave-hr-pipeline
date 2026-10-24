-- ============================================================
-- Stage 4: 01_dims.sql
-- Star schema dimension tables
-- SQLite-compatible (warehouse__ prefix)
-- ============================================================

-- ── dim_date ──────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS warehouse__dim_date;
CREATE TABLE warehouse__dim_date (
    date_key        TEXT PRIMARY KEY,   -- YYYY-MM-DD
    year            INTEGER NOT NULL,
    quarter         INTEGER NOT NULL,
    month           INTEGER NOT NULL,
    month_name      TEXT    NOT NULL,
    week_of_year    INTEGER NOT NULL,
    day_of_week     INTEGER NOT NULL,   -- 0=Sun … 6=Sat
    day_name        TEXT    NOT NULL,
    is_weekend      INTEGER NOT NULL DEFAULT 0,
    is_holiday      INTEGER NOT NULL DEFAULT 0,
    holiday_name    TEXT
);

-- ── dim_department ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS warehouse__dim_department;
CREATE TABLE warehouse__dim_department (
    dept_key        INTEGER PRIMARY KEY AUTOINCREMENT,
    dept_id         TEXT    NOT NULL UNIQUE,
    dept_name       TEXT    NOT NULL,
    plant           TEXT,
    cost_center     TEXT,
    previous_name   TEXT,
    renamed_on      TEXT
);

-- ── dim_shift ─────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS warehouse__dim_shift;
CREATE TABLE warehouse__dim_shift (
    shift_key       INTEGER PRIMARY KEY AUTOINCREMENT,
    shift_code      TEXT    NOT NULL UNIQUE,
    shift_name      TEXT    NOT NULL,
    start_time      TEXT    NOT NULL,  -- HH:MM
    end_time        TEXT    NOT NULL,
    crosses_midnight INTEGER NOT NULL DEFAULT 0,
    grace_minutes   INTEGER DEFAULT 10,
    shift_duration_hrs REAL
);

-- ── dim_employee (SCD Type 2) ─────────────────────────────────────────────────
-- One row per version of an employee record.
-- valid_from / valid_to derived from employment_history effective dates.
DROP TABLE IF EXISTS warehouse__dim_employee;
CREATE TABLE warehouse__dim_employee (
    emp_key         INTEGER PRIMARY KEY AUTOINCREMENT,
    emp_id          TEXT    NOT NULL,
    full_name       TEXT,
    gender          TEXT,
    dept_id         TEXT,
    dept_name       TEXT,
    designation     TEXT,
    grade           TEXT,
    employment_type TEXT,   -- Permanent, Contract
    plant           TEXT,
    basic_salary    REAL,
    annual_leave_entitlement INTEGER DEFAULT 21,
    hire_date       TEXT,
    separation_date TEXT,
    valid_from      TEXT    NOT NULL,
    valid_to        TEXT    NOT NULL DEFAULT '9999-12-31',
    is_current      INTEGER NOT NULL DEFAULT 1,
    is_active       INTEGER NOT NULL DEFAULT 1,
    UNIQUE (emp_id, valid_from)
);
CREATE INDEX IF NOT EXISTS idx_dim_emp_id      ON warehouse__dim_employee(emp_id);
CREATE INDEX IF NOT EXISTS idx_dim_emp_valid   ON warehouse__dim_employee(valid_from, valid_to);
