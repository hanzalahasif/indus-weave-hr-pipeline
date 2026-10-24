-- Q05: OT hours — computed from punches vs approved vs paid, by department and month
-- The central overtime analysis for the CFO

WITH ot_punches AS (
    SELECT
        STRFTIME('%Y-%m', fad.date_key) AS pay_month,
        COALESCE(de.dept_name, 'Unknown') AS dept_name,
        de.plant,
        SUM(fad.ot_hours_from_punches)  AS ot_hours_biometric
    FROM warehouse__fact_attendance_daily fad
    JOIN warehouse__dim_employee de ON fad.emp_key = de.emp_key
    GROUP BY pay_month, dept_name, de.plant
),
ot_approved AS (
    SELECT
        STRFTIME('%Y-%m', foa.date_key) AS pay_month,
        COALESCE(de.dept_name, 'Unknown') AS dept_name,
        de.plant,
        SUM(CASE WHEN foa.ot_status = 'Approved' THEN foa.approved_hours ELSE 0 END) AS ot_hours_approved
    FROM warehouse__fact_overtime_approved foa
    JOIN warehouse__dim_employee de ON foa.emp_key = de.emp_key
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
    COALESCE(p.pay_month, a.pay_month, pd.pay_month) AS pay_month,
    COALESCE(p.dept_name, a.dept_name, pd.dept_name) AS department,
    COALESCE(p.plant,     a.plant,     pd.plant)     AS plant,
    ROUND(COALESCE(p.ot_hours_biometric, 0), 2)      AS ot_hours_biometric,
    ROUND(COALESCE(a.ot_hours_approved,  0), 2)      AS ot_hours_approved,
    ROUND(COALESCE(pd.ot_hours_paid,     0), 2)      AS ot_hours_paid,
    ROUND(COALESCE(pd.ot_amount_paid,    0), 2)      AS ot_amount_paid
FROM ot_punches p
FULL OUTER JOIN ot_approved a  ON p.pay_month = a.pay_month AND p.dept_name = a.dept_name AND p.plant = a.plant
FULL OUTER JOIN ot_paid     pd ON COALESCE(p.pay_month, a.pay_month) = pd.pay_month
                              AND COALESCE(p.dept_name, a.dept_name) = pd.dept_name
                              AND COALESCE(p.plant, a.plant) = pd.plant
ORDER BY pay_month, plant, department;
