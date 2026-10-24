-- Q03: Absenteeism rate by plant and month (excluding approved leave)
-- Absenteeism = Absent days ÷ scheduled working days (non-Holiday, non-WeeklyOff)

WITH base AS (
    SELECT
        STRFTIME('%Y-%m', fad.date_key) AS pay_month,
        de.plant,
        SUM(CASE WHEN fad.attendance_status = 'Absent' THEN 1 ELSE 0 END) AS absent_days,
        SUM(CASE WHEN fad.attendance_status NOT IN ('Holiday','Weekly Off') THEN 1 ELSE 0 END) AS scheduled_days
    FROM warehouse__fact_attendance_daily fad
    JOIN warehouse__dim_employee de
         ON fad.emp_key = de.emp_key
    GROUP BY pay_month, de.plant
)
SELECT
    pay_month,
    plant,
    absent_days,
    scheduled_days,
    ROUND(absent_days * 100.0 / NULLIF(scheduled_days, 0), 2) AS absenteeism_pct
FROM base
ORDER BY pay_month, plant;
