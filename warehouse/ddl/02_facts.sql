-- SQL Server star-schema facts.
DROP TABLE IF EXISTS warehouse__fact_attendance_daily;
DROP TABLE IF EXISTS warehouse__fact_leave_day;
DROP TABLE IF EXISTS warehouse__fact_overtime_approved;
DROP TABLE IF EXISTS warehouse__fact_payroll_line;

CREATE TABLE warehouse__fact_attendance_daily (
    attendance_key      INT IDENTITY(1,1) PRIMARY KEY,
    date_key            VARCHAR(10) NOT NULL REFERENCES warehouse__dim_date(date_key),
    emp_key             INT NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    shift_key           INT REFERENCES warehouse__dim_shift(shift_key),
    dept_key            INT REFERENCES warehouse__dim_department(dept_key),
    attendance_status   NVARCHAR(30) NOT NULL
                        CHECK (attendance_status IN
                               ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')),
    punch_count         INT DEFAULT 0,
    first_in_ts         VARCHAR(30),
    last_out_ts         VARCHAR(30),
    worked_hours        FLOAT DEFAULT 0,
    late_minutes        FLOAT DEFAULT 0,
    early_departure_min FLOAT DEFAULT 0,
    ot_hours_from_punches FLOAT DEFAULT 0
);
CREATE INDEX idx_fad_date ON warehouse__fact_attendance_daily(date_key);
CREATE INDEX idx_fad_emp ON warehouse__fact_attendance_daily(emp_key);
CREATE INDEX idx_fad_dept ON warehouse__fact_attendance_daily(dept_key);

CREATE TABLE warehouse__fact_leave_day (
    leave_day_key   INT IDENTITY(1,1) PRIMARY KEY,
    date_key        VARCHAR(10) NOT NULL REFERENCES warehouse__dim_date(date_key),
    emp_key         INT NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    dept_key        INT REFERENCES warehouse__dim_department(dept_key),
    request_id      NVARCHAR(100) NOT NULL,
    leave_type      NVARCHAR(50) NOT NULL
);
CREATE INDEX idx_fld_date ON warehouse__fact_leave_day(date_key);
CREATE INDEX idx_fld_emp ON warehouse__fact_leave_day(emp_key);

CREATE TABLE warehouse__fact_overtime_approved (
    ot_key          INT IDENTITY(1,1) PRIMARY KEY,
    date_key        VARCHAR(10) NOT NULL REFERENCES warehouse__dim_date(date_key),
    emp_key         INT NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    dept_key        INT REFERENCES warehouse__dim_department(dept_key),
    request_id      NVARCHAR(100) NOT NULL,
    requested_hours FLOAT DEFAULT 0,
    approved_hours  FLOAT DEFAULT 0,
    ot_status       NVARCHAR(50) NOT NULL,
    approver_id     NVARCHAR(100)
);
CREATE INDEX idx_foa_date ON warehouse__fact_overtime_approved(date_key);
CREATE INDEX idx_foa_emp ON warehouse__fact_overtime_approved(emp_key);

CREATE TABLE warehouse__fact_payroll_line (
    payroll_key     INT IDENTITY(1,1) PRIMARY KEY,
    date_key        VARCHAR(10) NOT NULL REFERENCES warehouse__dim_date(date_key),
    emp_key         INT NOT NULL REFERENCES warehouse__dim_employee(emp_key),
    dept_key        INT REFERENCES warehouse__dim_department(dept_key),
    line_id         NVARCHAR(100) NOT NULL,
    pay_month       VARCHAR(7) NOT NULL,
    component       NVARCHAR(100) NOT NULL,
    component_type  NVARCHAR(50) NOT NULL,
    units           FLOAT,
    amount          FLOAT NOT NULL
);
CREATE INDEX idx_fpl_emp_month ON warehouse__fact_payroll_line(emp_key, pay_month);
CREATE INDEX idx_fpl_component ON warehouse__fact_payroll_line(component);
