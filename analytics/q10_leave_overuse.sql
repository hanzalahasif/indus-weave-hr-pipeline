-- Q10: Employees whose approved Annual Leave in these 6 months already
--       exceeds their full-year entitlement (Rule 18)

WITH annual_leave_used AS (
    SELECT
        de.emp_id,
        de.full_name,
        COALESCE(de.dept_name, 'Unknown') AS department,
        de.plant,
        COALESCE(de.annual_leave_entitlement, 21) AS annual_entitlement,
        COUNT(fld.leave_day_key) AS leave_days_taken
    FROM warehouse__fact_leave_day fld
    JOIN warehouse__dim_employee de ON fld.emp_key = de.emp_key
    WHERE UPPER(fld.leave_type) IN ('ANNUAL', 'ANNUAL LEAVE', 'AL')
      AND fld.date_key BETWEEN '2026-04-01' AND '2026-09-30'
    GROUP BY de.emp_id, de.full_name, department, de.plant, annual_entitlement
)
SELECT
    emp_id,
    full_name,
    department,
    plant,
    leave_days_taken,
    annual_entitlement AS full_year_entitlement,
    leave_days_taken - annual_entitlement AS days_over_entitlement
FROM annual_leave_used
WHERE leave_days_taken > annual_entitlement
ORDER BY days_over_entitlement DESC;
