-- Q07: Employees paid in a month with zero attendance in that month
-- Ghost payroll risk — critical CFO finding

WITH paid_months AS (
    SELECT DISTINCT
        fpl.emp_key,
        fpl.pay_month
    FROM warehouse__fact_payroll_line fpl
    WHERE fpl.component_type = 'EARNING'
),
attendance_months AS (
    SELECT
        fad.emp_key,
        STRFTIME('%Y-%m', fad.date_key) AS pay_month,
        SUM(CASE WHEN fad.attendance_status = 'Present' THEN 1 ELSE 0 END) AS present_days
    FROM warehouse__fact_attendance_daily fad
    GROUP BY fad.emp_key, pay_month
)
SELECT
    pm.pay_month,
    de.emp_id,
    de.full_name,
    COALESCE(de.dept_name, 'Unknown') AS department,
    de.plant,
    COALESCE(am.present_days, 0) AS present_days
FROM paid_months pm
LEFT JOIN attendance_months am ON pm.emp_key = am.emp_key AND pm.pay_month = am.pay_month
JOIN warehouse__dim_employee de ON pm.emp_key = de.emp_key
WHERE COALESCE(am.present_days, 0) = 0
ORDER BY pm.pay_month, department, de.emp_id;
