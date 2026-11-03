-- SQL Server warehouse load. Run after stages 1-3.

;WITH cal AS (
    SELECT CAST('2026-04-01' AS DATE) AS calendar_date
    UNION ALL
    SELECT DATEADD(DAY, 1, calendar_date)
    FROM cal
    WHERE calendar_date < '2026-09-30'
)
INSERT INTO warehouse__dim_date (
    date_key, year, quarter, month, month_name,
    week_of_year, day_of_week, day_name, is_weekend, is_holiday, holiday_name
)
SELECT
    CONVERT(VARCHAR(10), calendar_date, 23),
    YEAR(calendar_date),
    DATEPART(QUARTER, calendar_date),
    MONTH(calendar_date),
    DATENAME(MONTH, calendar_date),
    DATEPART(ISO_WEEK, calendar_date),
    (DATEDIFF(DAY, '19000107', calendar_date) % 7 + 7) % 7,
    DATENAME(WEEKDAY, calendar_date),
    CASE WHEN (DATEDIFF(DAY, '19000107', calendar_date) % 7 + 7) % 7 IN (0, 6) THEN 1 ELSE 0 END,
    0,
    NULL
FROM cal
OPTION (MAXRECURSION 0);

UPDATE dd
SET is_holiday = 1,
    holiday_name = (
        SELECT TOP (1) h.holiday_name
        FROM staging__holidays h
        WHERE h.holiday_date = dd.date_key
        ORDER BY h.holiday_name
    )
FROM warehouse__dim_date dd
WHERE EXISTS (
    SELECT 1 FROM staging__holidays h WHERE h.holiday_date = dd.date_key
);

INSERT INTO warehouse__dim_department (
    dept_id, dept_name, plant, cost_center, previous_name, renamed_on
)
SELECT DISTINCT dept_id, dept_name, plant, cost_center, previous_name, renamed_on
FROM staging__departments;

INSERT INTO warehouse__dim_shift (
    shift_code, shift_name, start_time, end_time, crosses_midnight, grace_minutes, shift_duration_hrs
)
SELECT
    shift_code,
    name,
    start_time,
    end_time,
    CASE WHEN LOWER(CONVERT(VARCHAR(10), crosses_midnight)) IN ('true', '1') THEN 1 ELSE 0 END,
    COALESCE(TRY_CAST(grace_minutes AS INT), 10),
    CASE
        WHEN LOWER(CONVERT(VARCHAR(10), crosses_midnight)) IN ('true', '1')
        THEN ROUND(
            ((TRY_CAST(SUBSTRING(end_time, 1, 2) AS FLOAT) * 60 + TRY_CAST(SUBSTRING(end_time, 4, 2) AS FLOAT))
            + 1440
            - (TRY_CAST(SUBSTRING(start_time, 1, 2) AS FLOAT) * 60 + TRY_CAST(SUBSTRING(start_time, 4, 2) AS FLOAT))
            ) / 60, 2)
        ELSE ROUND(
            ((TRY_CAST(SUBSTRING(end_time, 1, 2) AS FLOAT) * 60 + TRY_CAST(SUBSTRING(end_time, 4, 2) AS FLOAT))
            - (TRY_CAST(SUBSTRING(start_time, 1, 2) AS FLOAT) * 60 + TRY_CAST(SUBSTRING(start_time, 4, 2) AS FLOAT))
            ) / 60, 2)
    END
FROM staging__shifts;

INSERT INTO warehouse__dim_employee (
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
    TRY_CAST(h.basic_salary AS FLOAT),
    COALESCE(TRY_CAST(e.annual_leave_entitlement AS INT), 21),
    e.hire_date,
    e.separation_date,
    h.valid_from,
    h.valid_to,
    CASE WHEN h.valid_to = '9999-12-31' THEN 1 ELSE 0 END,
    CASE WHEN e.separation_date IS NULL OR e.separation_date = ''
              OR e.separation_date >= '2026-09-30' THEN 1 ELSE 0 END
FROM staging__employment_history h
LEFT JOIN staging__employees e ON e.emp_id = h.emp_id
LEFT JOIN staging__departments d ON d.dept_id = h.dept_id;

INSERT INTO warehouse__fact_attendance_daily (
    date_key, emp_key, shift_key, dept_key,
    attendance_status, punch_count, first_in_ts, last_out_ts,
    worked_hours, late_minutes, early_departure_min, ot_hours_from_punches
)
SELECT
    a.work_date, de.emp_key, ds.shift_key, dd.dept_key,
    a.attendance_status, a.punch_count, a.first_in, a.last_out,
    a.worked_hours, a.late_minutes, a.early_departure_minutes, a.ot_hours_from_punches
FROM staging__attendance_daily a
JOIN warehouse__dim_employee de
  ON de.emp_id = a.emp_id AND a.work_date BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_shift ds ON ds.shift_code = a.shift_code
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;

INSERT INTO warehouse__fact_leave_day (
    date_key, emp_key, dept_key, request_id, leave_type
)
SELECT ld.leave_date, de.emp_key, dd.dept_key, ld.request_id, ld.leave_type
FROM staging__leave_days ld
JOIN warehouse__dim_employee de
  ON de.emp_id = ld.emp_id AND ld.leave_date BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;

INSERT INTO warehouse__fact_overtime_approved (
    date_key, emp_key, dept_key, request_id, requested_hours, approved_hours, ot_status, approver_id
)
SELECT
    ot.ot_date, de.emp_key, dd.dept_key, ot.request_id,
    TRY_CAST(ot.requested_hours AS FLOAT), TRY_CAST(ot.approved_hours AS FLOAT),
    ot.status, ot.approver_id
FROM staging__overtime_requests ot
JOIN warehouse__dim_employee de
  ON de.emp_id = ot.emp_id AND ot.ot_date BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;

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
        ELSE CONCAT(pl.payroll_month, '-01')
    END,
    de.emp_key, dd.dept_key, pl.line_id, pl.payroll_month,
    pl.component, pl.component_type,
    TRY_CAST(pl.units AS FLOAT), TRY_CAST(pl.amount AS FLOAT)
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
            ELSE CONCAT(pl.payroll_month, '-01')
        END
     ) BETWEEN de.valid_from AND de.valid_to
LEFT JOIN warehouse__dim_department dd ON dd.dept_id = de.dept_id;
