-- Q03: Absenteeism rate by plant and month (excluding approved leave)
-- Absenteeism = Absent days ÷ scheduled working days (non-Holiday, non-WeeklyOff)

WITH base AS (
    SELECT
        CONVERT(CHAR(7), fad.date_key, 120) AS pay_month,
        de.plant,
        SUM(CASE WHEN fad.attendance_status = 'Absent' THEN 1 ELSE 0 END) AS absent_days,
        SUM(CASE WHEN fad.attendance_status NOT IN ('Holiday','Weekly Off') THEN 1 ELSE 0 END) AS scheduled_days
    FROM warehouse__fact_attendance_daily fad
    JOIN warehouse__dim_employee de
         ON fad.emp_key = de.emp_key
    GROUP BY CONVERT(CHAR(7), fad.date_key, 120), de.plant
)
SELECT
    pay_month,
    plant,
    absent_days,
    scheduled_days,
    ROUND(absent_days * 100.0 / NULLIF(scheduled_days, 0), 2) AS absenteeism_pct
FROM base
ORDER BY pay_month, plant;
