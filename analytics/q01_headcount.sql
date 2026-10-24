-- Q01: Month-end headcount by plant and department, all six months
-- Rule 3: Monthly figures belong to department on last day of month
-- Rule 4: In headcount if hire_date <= month_end and (separation_date IS NULL OR separation_date > month_end)

WITH month_ends AS (
    SELECT '2026-04-30' AS month_end UNION ALL
    SELECT '2026-05-31' UNION ALL
    SELECT '2026-06-30' UNION ALL
    SELECT '2026-07-31' UNION ALL
    SELECT '2026-08-31' UNION ALL
    SELECT '2026-09-30'
),
active_on_month_end AS (
    SELECT
        me.month_end,
        de.plant,
        COALESCE(de.dept_name, 'Unknown') AS department,
        COUNT(DISTINCT de.emp_id) AS headcount
    FROM month_ends me
    JOIN warehouse__dim_employee de
         ON me.month_end BETWEEN de.valid_from AND de.valid_to
    WHERE de.hire_date <= me.month_end
      AND (de.separation_date IS NULL OR de.separation_date = '' OR de.separation_date > me.month_end)
    GROUP BY me.month_end, de.plant, department
)
SELECT
    month_end,
    plant,
    department,
    headcount
FROM active_on_month_end
ORDER BY month_end, plant, department;
