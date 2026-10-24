-- Q08: Employees still receiving pay after their separation date
-- Zombie payroll — direct financial exposure

SELECT
    fpl.pay_month,
    de.emp_id,
    de.full_name,
    COALESCE(de.dept_name, 'Unknown') AS department,
    de.plant,
    de.separation_date,
    SUM(fpl.amount) AS total_paid
FROM warehouse__fact_payroll_line fpl
JOIN warehouse__dim_employee de ON fpl.emp_key = de.emp_key
WHERE de.separation_date IS NOT NULL
  AND de.separation_date <> ''
  AND de.separation_date <> 'None'
  AND fpl.pay_month > SUBSTR(de.separation_date, 1, 7)
  AND fpl.component_type = 'EARNING'
GROUP BY fpl.pay_month, de.emp_id, de.full_name, department, de.plant, de.separation_date
ORDER BY de.separation_date, fpl.pay_month;
