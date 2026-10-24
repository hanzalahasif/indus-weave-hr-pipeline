-- Q06: Departments where paid OT exceeds computed OT by more than 15%
-- Comparing paid OT hours (payroll_lines units) against actual biometric punch OT hours

WITH ot_summary AS (
    SELECT
        STRFTIME('%Y-%m', fad.date_key) AS pay_month,
        COALESCE(de.dept_name, 'Unknown') AS dept_name,
        de.plant,
        SUM(fad.ot_hours_from_punches) AS ot_hours_biometric
    FROM warehouse__fact_attendance_daily fad
    JOIN warehouse__dim_employee de ON fad.emp_key = de.emp_key
    GROUP BY pay_month, dept_name, de.plant
),
ot_paid AS (
    SELECT
        fpl.pay_month,
        COALESCE(de.dept_name, 'Unknown') AS dept_name,
        de.plant,
        SUM(fpl.units)  AS ot_hours_paid,
        SUM(fpl.amount) AS ot_amount_paid
    FROM warehouse__fact_payroll_line fpl
    JOIN warehouse__dim_employee de ON fpl.emp_key = de.emp_key
    WHERE fpl.component = 'OVERTIME'
    GROUP BY fpl.pay_month, dept_name, de.plant
)
SELECT
    s.pay_month,
    s.dept_name AS department,
    s.plant,
    ROUND(s.ot_hours_biometric, 2) AS biometric_ot_hours,
    ROUND(p.ot_hours_paid, 2)      AS paid_ot_hours,
    ROUND(p.ot_amount_paid, 2)     AS paid_ot_amount,
    ROUND((p.ot_hours_paid - s.ot_hours_biometric), 2) AS excess_hours,
    ROUND(
        (p.ot_hours_paid - s.ot_hours_biometric) * 100.0 / NULLIF(s.ot_hours_biometric, 0),
        1
    ) AS excess_pct
FROM ot_summary s
JOIN ot_paid p ON s.pay_month = p.pay_month AND s.dept_name = p.dept_name AND s.plant = p.plant
WHERE p.ot_hours_paid > s.ot_hours_biometric * 1.15
ORDER BY excess_pct DESC;
