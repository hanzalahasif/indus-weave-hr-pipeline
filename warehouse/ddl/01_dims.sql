-- SQL Server star-schema dimensions.
DROP TABLE IF EXISTS warehouse__fact_attendance_daily;
DROP TABLE IF EXISTS warehouse__fact_leave_day;
DROP TABLE IF EXISTS warehouse__fact_overtime_approved;
DROP TABLE IF EXISTS warehouse__fact_payroll_line;

DROP TABLE IF EXISTS warehouse__dim_employee;
DROP TABLE IF EXISTS warehouse__dim_shift;
DROP TABLE IF EXISTS warehouse__dim_department;
DROP TABLE IF EXISTS warehouse__dim_date;

CREATE TABLE warehouse__dim_date (
    date_key        VARCHAR(10) PRIMARY KEY,
    year            INT NOT NULL,
    quarter         INT NOT NULL,
    month           INT NOT NULL,
    month_name      NVARCHAR(20) NOT NULL,
    week_of_year    INT NOT NULL,
    day_of_week     INT NOT NULL,
    day_name        NVARCHAR(20) NOT NULL,
    is_weekend      BIT NOT NULL DEFAULT 0,
    is_holiday      BIT NOT NULL DEFAULT 0,
    holiday_name    NVARCHAR(200)
);

CREATE TABLE warehouse__dim_department (
    dept_key        INT IDENTITY(1,1) PRIMARY KEY,
    dept_id         NVARCHAR(100) NOT NULL UNIQUE,
    dept_name       NVARCHAR(200) NOT NULL,
    plant           NVARCHAR(100),
    cost_center     NVARCHAR(100),
    previous_name   NVARCHAR(200),
    renamed_on      VARCHAR(10)
);

CREATE TABLE warehouse__dim_shift (
    shift_key       INT IDENTITY(1,1) PRIMARY KEY,
    shift_code      NVARCHAR(30) NOT NULL UNIQUE,
    shift_name      NVARCHAR(100) NOT NULL,
    start_time      VARCHAR(5) NOT NULL,
    end_time        VARCHAR(5) NOT NULL,
    crosses_midnight BIT NOT NULL DEFAULT 0,
    grace_minutes   INT DEFAULT 10,
    shift_duration_hrs REAL
);

CREATE TABLE warehouse__dim_employee (
    emp_key         INT IDENTITY(1,1) PRIMARY KEY,
    emp_id          NVARCHAR(100) NOT NULL,
    full_name       NVARCHAR(200),
    gender          NVARCHAR(30),
    dept_id         NVARCHAR(100),
    dept_name       NVARCHAR(200),
    designation     NVARCHAR(150),
    grade           NVARCHAR(50),
    employment_type NVARCHAR(50),
    plant           NVARCHAR(100),
    basic_salary    FLOAT,
    annual_leave_entitlement INT DEFAULT 21,
    hire_date       VARCHAR(10),
    separation_date VARCHAR(10),
    valid_from      VARCHAR(10) NOT NULL,
    valid_to        VARCHAR(10) NOT NULL DEFAULT '9999-12-31',
    is_current      BIT NOT NULL DEFAULT 1,
    is_active       BIT NOT NULL DEFAULT 1,
    UNIQUE (emp_id, valid_from)
);

CREATE INDEX idx_dim_emp_id ON warehouse__dim_employee(emp_id);
CREATE INDEX idx_dim_emp_valid ON warehouse__dim_employee(valid_from, valid_to);
