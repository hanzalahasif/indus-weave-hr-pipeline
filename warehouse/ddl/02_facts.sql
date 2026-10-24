-- ============================================================
-- Stage 4: 02_facts.sql
-- Star schema fact tables
-- ============================================================

-- ── fact_attendance_daily ─────────────────────────────────────────────────────
DROP TABLE IF EXISTS warehouse__fact_attendance_daily;
CREATE TABLE warehouse__fact_attendance_daily (
    attendance_key      INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key            TEXT    NOT NULL REFERENCES warehouse__dim_date(date_key),
    emp_key             INTEGER NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    shift_key           INTEGER REFERENCES warehouse__dim_shift(shift_key),
    dept_key            INTEGER REFERENCES warehouse__dim_department(dept_key),

    -- Measures
    attendance_status   TEXT    NOT NULL
                        CHECK (attendance_status IN
                               ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')),
    punch_count         INTEGER DEFAULT 0,
    first_in_ts         TEXT,
    last_out_ts         TEXT,
    worked_hours        REAL    DEFAULT 0,
    late_minutes        REAL    DEFAULT 0,
    early_departure_min REAL    DEFAULT 0,
    ot_hours_from_punches REAL  DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fad_date    ON warehouse__fact_attendance_daily(date_key);
CREATE INDEX IF NOT EXISTS idx_fad_emp     ON warehouse__fact_attendance_daily(emp_key);
CREATE INDEX IF NOT EXISTS idx_fad_dept    ON warehouse__fact_attendance_daily(dept_key);

-- ── fact_leave_day ────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS warehouse__fact_leave_day;
CREATE TABLE warehouse__fact_leave_day (
    leave_day_key   INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key        TEXT    NOT NULL REFERENCES warehouse__dim_date(date_key),
    emp_key         INTEGER NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    dept_key        INTEGER REFERENCES warehouse__dim_department(dept_key),
    request_id      TEXT    NOT NULL,
    leave_type      TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fld_date    ON warehouse__fact_leave_day(date_key);
CREATE INDEX IF NOT EXISTS idx_fld_emp     ON warehouse__fact_leave_day(emp_key);

-- ── fact_overtime_approved ────────────────────────────────────────────────────
DROP TABLE IF EXISTS warehouse__fact_overtime_approved;
CREATE TABLE warehouse__fact_overtime_approved (
    ot_key          INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key        TEXT    NOT NULL REFERENCES warehouse__dim_date(date_key),
    emp_key         INTEGER NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    dept_key        INTEGER REFERENCES warehouse__dim_department(dept_key),
    request_id      TEXT    NOT NULL,
    requested_hours REAL    DEFAULT 0,
    approved_hours  REAL    DEFAULT 0,
    ot_status       TEXT    NOT NULL,
    approver_id     TEXT
);
CREATE INDEX IF NOT EXISTS idx_foa_date    ON warehouse__fact_overtime_approved(date_key);
CREATE INDEX IF NOT EXISTS idx_foa_emp     ON warehouse__fact_overtime_approved(emp_key);

-- ── fact_payroll_line ─────────────────────────────────────────────────────────
DROP TABLE IF EXISTS warehouse__fact_payroll_line;
CREATE TABLE warehouse__fact_payroll_line (
    payroll_key     INTEGER PRIMARY KEY AUTOINCREMENT,
    date_key        TEXT    NOT NULL REFERENCES warehouse__dim_date(date_key),  -- month-end date
    emp_key         INTEGER NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    dept_key        INTEGER REFERENCES warehouse__dim_department(dept_key),
    line_id         TEXT    NOT NULL,
    pay_month       TEXT    NOT NULL,  -- YYYY-MM
    component       TEXT    NOT NULL,
    component_type  TEXT    NOT NULL,
    units           REAL,
    amount          REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fpl_emp_month ON warehouse__fact_payroll_line(emp_key, pay_month);
CREATE INDEX IF NOT EXISTS idx_fpl_component ON warehouse__fact_payroll_line(component);
