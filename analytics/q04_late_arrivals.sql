-- Q04: Top 10 employees with the most late arrivals, and their department

SELECT
    de.emp_id,
    de.full_name,
    COALESCE(de.dept_name, 'Unknown') AS department,
    de.plant,
    COUNT(*) AS late_arrival_days
FROM warehouse__fact_attendance_daily fad
JOIN warehouse__dim_employee de ON fad.emp_key = de.emp_key
WHERE fad.attendance_status = 'Present'
  AND fad.late_minutes > 0
GROUP BY de.emp_id, de.full_name, department, de.plant
ORDER BY late_arrival_days DESC
LIMIT 10;
