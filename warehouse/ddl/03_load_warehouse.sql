-- ============================================================
-- Stage 4: 03_load_warehouse.sql
-- Populates warehouse dimensions and facts from staging tables.
-- Run AFTER all staging tables are built.
-- SQLite-compatible (staging__ and warehouse__ prefixes).
-- ============================================================

-- ── 1. dim_date ───────────────────────────────────────────────────────────────
WITH RECURSIVE cal(d) AS (
    SELECT DATE('2026-04-01')
    UNION ALL SELECT DATE(d, '+1 day') FROM cal WHERE d < '2026-09-30'
)
INSERT OR IGNORE INTO warehouse__dim_date (
    date_key, year, quarter, month, month_name,
    week_of_year, day_of_week, day_name, is_weekend, is_holiday, holiday_name
)
SELECT
    d,
    CAST(STRFTIME('%Y', d) AS INTEGER),
    CASE WHEN CAST(STRFTIME('%m',d) AS INT) BETWEEN 1 AND 3 THEN 1
         WHEN CAST(STRFTIME('%m',d) AS INT) BETWEEN 4 AND 6 THEN 2
         WHEN CAST(STRFTIME('%m',d) AS INT) BETWEEN 7 AND 9 THEN 3
         ELSE 4 END,
    CAST(STRFTIME('%m', d) AS INTEGER),
    CASE STRFTIME('%m', d)
        WHEN '01' THEN 'January'   WHEN '02' THEN 'February'
        WHEN '03' THEN 'March'     WHEN '04' THEN 'April'
        WHEN '05' THEN 'May'       WHEN '06' THEN 'June'
        WHEN '07' THEN 'July'      WHEN '08' THEN 'August'
        WHEN '09' THEN 'September' WHEN '10' THEN 'October'
        WHEN '11' THEN 'November'  ELSE 'December' END,
    CAST(STRFTIME('%W', d) AS INTEGER),
    CAST(STRFTIME('%w', d) AS INTEGER),
    CASE STRFTIME('%w', d)
        WHEN '0' THEN 'Sunday'    WHEN '1' THEN 'Monday'
        WHEN '2' THEN 'Tuesday'   WHEN '3' THEN 'Wednesday'
        WHEN '4' THEN 'Thursday'  WHEN '5' THEN 'Friday'
        ELSE 'Saturday' END,
    CASE WHEN STRFTIME('%w', d) IN ('0','6') THEN 1 ELSE 0 END,
    0, NULL
FROM cal;

-- Mark holidays in dim_date
UPDATE warehouse__dim_date
SET is_holiday   = 1,
    holiday_name = (SELECT holiday_name FROM staging__holidays h WHERE h.holiday_date = date_key LIMIT 1)
WHERE date_key IN (SELECT holiday_date FROM staging__holidays);

-- ── 2. dim_department ────────────────────────────────────────────────────────
INSERT OR IGNORE INTO warehouse__dim_department (
    dept_id, dept_name, plant, cost_center, previous_name, renamed_on
)
SELECT
    dept_id,
    dept_name,
    plant,
    cost_center,
    previous_name,
    renamed_on
FROM staging__departments;

-- ── 3. dim_shift ─────────────────────────────────────────────────────────────
INSERT OR IGNORE INTO warehouse__dim_shift (
    shift_code, shift_name, start_time, end_time, crosses_midnight, grace_minutes, shift_duration_hrs
)
SELECT
    shift_code,
    name,
    start_time,
    end_time,
    CASE WHEN crosses_midnight = 'True' OR crosses_midnight = '1' OR crosses_midnight = 1 THEN 1 ELSE 0 END,
    COALESCE(CAST(grace_minutes AS INTEGER), 10),
    CASE
        WHEN crosses_midnight = 'True' OR crosses_midnight = '1' OR crosses_midnight = 1
        THEN ROUND(
            ((CAST(SUBSTR(end_time,1,2) AS REAL)*60 + CAST(SUBSTR(end_time,4,2) AS REAL))
            + 1440
            - (CAST(SUBSTR(start_time,1,2) AS REAL)*60 + CAST(SUBSTR(start_time,4,2) AS REAL))
            ) / 60, 2)
        ELSE ROUND(
            ((CAST(SUBSTR(end_time,1,2) AS REAL)*60 + CAST(SUBSTR(end_time,4,2) AS REAL))
            - (CAST(SUBSTR(start_time,1,2) AS REAL)*60 + CAST(SUBSTR(start_time,4,2) AS REAL))
            ) / 60, 2)
    END
FROM staging__shifts;

-- ── 4. dim_employee (SCD Type 2) ─────────────────────────────────────────────
INSERT OR IGNORE INTO warehouse__dim_employee (
    emp_id, full_name, gender, dept_id, dept_name,
    designation, grade, employment_type, plant, basic_salary,
    annual_leave_entitlement, hire_date, separation_date,
    valid_from, valid_to, is_current, is_active
)
SELECT
    h.emp_id,
    e.full_name,
    e.gender,
    h.dept_id,
    d.dept_name,
    h.designation,
    h.grade,
    COALESCE(e.employment_type, 'Permanent'),
    e.plant,
    CAST(h.basic_salary AS REAL),
    COALESCE(CAST(e.annual_leave_entitlement AS INTEGER), 21),
    e.hire_date,
    e.separation_date,
    h.valid_from,
    h.valid_to,
    CASE WHEN h.valid_to = '9999-12-31' THEN 1 ELSE 0 END,
    CASE WHEN e.separation_date IS NULL OR e.separation_date = '' OR e.separation_date >= '2026-09-30' THEN 1 ELSE 0 END
FROM staging__employment_history h
LEFT JOIN staging__employees e ON e.emp_id = h.emp_id
LEFT JOIN staging__departments d ON d.dept_id = h.dept_id;

-- ── 5. fact_attendance_daily ─────────────────────────────────────────────────
INSERT INTO warehouse__fact_attendance_daily (
    date_key, emp_key, shift_key, dept_key,
    attendance_status, punch_count, first_in_ts, last_out_ts,
    worked_hours, late_minutes, early_departure_min, ot_hours_from_punches
)
SELECT
    a.work_date,
    de.emp_key,
    ds.shift_key,
    dd.dept_key,
    a.attendance_status,
    a.punch_count,
    a.first_in,
    a.last_out,
    a.worked_hours,
    a.late_minutes,
    a.early_departure_minutes,
    a.ot_hours_from_punches
FROM staging__attendance_daily a
JOIN warehouse__dim_employee de
     ON de.emp_id = a.emp_id
     AND a.work_date BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_shift ds ON ds.shift_code = a.shift_code
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;

-- ── 6. fact_leave_day ────────────────────────────────────────────────────────
INSERT INTO warehouse__fact_leave_day (
    date_key, emp_key, dept_key, request_id, leave_type
)
SELECT
    ld.leave_date,
    de.emp_key,
    dd.dept_key,
    ld.request_id,
    ld.leave_type
FROM staging__leave_days ld
JOIN warehouse__dim_employee de
     ON de.emp_id = ld.emp_id
     AND ld.leave_date BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;

-- ── 7. fact_overtime_approved ────────────────────────────────────────────────
INSERT INTO warehouse__fact_overtime_approved (
    date_key, emp_key, dept_key, request_id, requested_hours, approved_hours, ot_status, approver_id
)
SELECT
    ot.ot_date,
    de.emp_key,
    dd.dept_key,
    ot.request_id,
    CAST(ot.requested_hours AS REAL),
    CAST(ot.approved_hours AS REAL),
    ot.status,
    ot.approver_id
FROM staging__overtime_requests ot
JOIN warehouse__dim_employee de
     ON de.emp_id = ot.emp_id
     AND ot.ot_date BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;

-- ── 8. fact_payroll_line ─────────────────────────────────────────────────────
-- Rule 3: Monthly figures belong to department on last day of month (or separation date)
INSERT INTO warehouse__fact_payroll_line (
    date_key, emp_key, dept_key, line_id, pay_month, component, component_type, units, amount
)
SELECT
    CASE pl.payroll_month
        WHEN '2026-04' THEN '2026-04-30'
        WHEN '2026-05' THEN '2026-05-31'
        WHEN '2026-06' THEN '2026-06-30'
        WHEN '2026-07' THEN '2026-07-31'
        WHEN '2026-08' THEN '2026-08-31'
        WHEN '2026-09' THEN '2026-09-30'
        ELSE pl.payroll_month || '-01'
    END AS date_key,
    de.emp_key,
    dd.dept_key,
    pl.line_id,
    pl.payroll_month,
    pl.component,
    pl.component_type,
    CAST(pl.units AS REAL),
    CAST(pl.amount AS REAL)
FROM staging__payroll_lines pl
JOIN warehouse__dim_employee de
     ON de.emp_id = pl.emp_id
     AND (
         CASE pl.payroll_month
             WHEN '2026-04' THEN '2026-04-30'
             WHEN '2026-05' THEN '2026-05-31'
             WHEN '2026-06' THEN '2026-06-30'
             WHEN '2026-07' THEN '2026-07-31'
             WHEN '2026-08' THEN '2026-08-31'
             WHEN '2026-09' THEN '2026-09-30'
             ELSE pl.payroll_month || '-01'
         END
     ) BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;
