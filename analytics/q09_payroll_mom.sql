-- Q09: Payroll cost per employee by department, with month-over-month change
-- Rule 21: Payroll cost = sum of EARNING lines
-- Uses LAG() window function for MoM delta

WITH monthly_cost AS (
    SELECT
        fpl.pay_month,
        de.emp_id,
        de.full_name,
        COALESCE(de.dept_name, 'Unknown') AS dept_name,
        de.plant,
        SUM(fpl.amount) AS total_cost
    FROM warehouse__fact_payroll_line fpl
    JOIN warehouse__dim_employee de ON fpl.emp_key = de.emp_key
    WHERE fpl.component_type = 'EARNING'
    GROUP BY fpl.pay_month, de.emp_id, de.full_name, dept_name, de.plant
),
with_lag AS (
    SELECT
        pay_month,
        emp_id,
        full_name,
        dept_name,
        plant,
        total_cost,
        LAG(total_cost) OVER (
            PARTITION BY emp_id
            ORDER BY pay_month
        ) AS prev_month_cost
    FROM monthly_cost
)
SELECT
    pay_month,
    emp_id,
    full_name,
    dept_name AS department,
    plant,
    ROUND(total_cost, 2)                                        AS total_cost,
    ROUND(prev_month_cost, 2)                                   AS prev_month_cost,
    ROUND(total_cost - COALESCE(prev_month_cost, 0), 2)        AS mom_change,
    ROUND(
        (total_cost - prev_month_cost) * 100.0 / NULLIF(prev_month_cost, 0),
        1
    )                                                           AS mom_change_pct
FROM with_lag
ORDER BY pay_month, department, emp_id;
