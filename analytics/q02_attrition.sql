-- Q02: Monthly attrition rate by department
-- Attrition = separations in the month ÷ average headcount
-- Separation = employee whose separation_date falls within the month

WITH month_list AS (
    SELECT '2026-04' AS m, '2026-04-01' AS m_start, '2026-04-30' AS m_end UNION ALL
    SELECT '2026-05',      '2026-05-01', '2026-05-31' UNION ALL
    SELECT '2026-06',      '2026-06-01', '2026-06-30' UNION ALL
    SELECT '2026-07',      '2026-07-01', '2026-07-31' UNION ALL
    SELECT '2026-08',      '2026-08-01', '2026-08-31' UNION ALL
    SELECT '2026-09',      '2026-09-01', '2026-09-30'
),
separations AS (
    SELECT
        ml.m AS pay_month,
        COALESCE(de.dept_name, 'Unknown') AS department,
        COUNT(DISTINCT de.emp_id) AS separations
    FROM month_list ml
    JOIN warehouse__dim_employee de
         ON de.separation_date BETWEEN ml.m_start AND ml.m_end
         AND de.separation_date BETWEEN de.valid_from AND de.valid_to
    GROUP BY ml.m, department
),
avg_headcount AS (
    SELECT
        ml.m AS pay_month,
        COALESCE(de.dept_name, 'Unknown') AS department,
        (
            COUNT(DISTINCT CASE
                WHEN de.hire_date <= ml.m_start
                 AND (de.separation_date IS NULL OR de.separation_date = '' OR de.separation_date >= ml.m_start)
                 AND ml.m_start BETWEEN de.valid_from AND de.valid_to
                THEN de.emp_id END)
            +
            COUNT(DISTINCT CASE
                WHEN de.hire_date <= ml.m_end
                 AND (de.separation_date IS NULL OR de.separation_date = '' OR de.separation_date >= ml.m_end)
                 AND ml.m_end BETWEEN de.valid_from AND de.valid_to
                THEN de.emp_id END)
        ) / 2.0 AS avg_hc
    FROM month_list ml
    JOIN warehouse__dim_employee de
         ON (ml.m_start BETWEEN de.valid_from AND de.valid_to OR ml.m_end BETWEEN de.valid_from AND de.valid_to)
    GROUP BY ml.m, department
)
SELECT
    ah.pay_month,
    ah.department,
    COALESCE(s.separations, 0)                            AS separations,
    ROUND(ah.avg_hc, 1)                                   AS avg_headcount,
    ROUND(COALESCE(s.separations, 0) * 100.0 / NULLIF(ah.avg_hc, 0), 2) AS attrition_pct
FROM avg_headcount ah
LEFT JOIN separations s ON s.pay_month = ah.pay_month AND s.department = ah.department
ORDER BY ah.pay_month, ah.department;
