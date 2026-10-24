-- ============================================================
-- Stage 3: attendance_daily.sql
-- Builds staging.attendance_daily
-- One row per employee per scheduled working day (Apr–Sep 2026)
--
-- Logic order:
--   1. Fill roster gaps (carry forward previous week's shift)
--   2. Pair first check-in / last check-out per shift per employee
--      • Night shift: assign punch to shift start date
--   3. Calculate worked hours, late minutes, early-departure minutes, OT hours
--   4. Assign status in priority:
--      Holiday → Weekly Off → On Leave → Present → Missing Punch → Absent
-- ============================================================

-- ── STEP 0: helper – date spine (Apr 1 – Sep 30 2026) ────────────────────────
-- SQLite-compatible recursive CTE
WITH RECURSIVE date_spine(work_date) AS (
    SELECT DATE('2026-04-01')
    UNION ALL
    SELECT DATE(work_date, '+1 day')
    FROM date_spine
    WHERE work_date < DATE('2026-09-30')
),

-- ── STEP 1: fill roster gaps ──────────────────────────────────────────────────
-- Roster has one row per emp_id per ISO week. A missing week = same shift as
-- previous week. We use LAG / last-value pattern via a recursive fill.
roster_raw AS (
    SELECT
        emp_id,
        week_start_date,   -- assumed column name; adjust if needed
        shift_id
    FROM staging__shift_roster   -- adjust prefix for PG: staging.shift_roster
),
roster_with_dates AS (
    -- Expand each roster week into 7 daily rows
    SELECT
        r.emp_id,
        DATE(r.week_start_date, '+' || offs.n || ' days') AS roster_date,
        r.shift_id
    FROM roster_raw r
    CROSS JOIN (
        SELECT 0 AS n UNION ALL SELECT 1 UNION ALL SELECT 2
        UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5 UNION ALL SELECT 6
    ) offs
),
-- For each employee × date, pick the most recent roster entry on or before that date
roster_filled AS (
    SELECT
        ds.work_date,
        e.emp_id,
        (
            SELECT shift_id
            FROM roster_with_dates rwd
            WHERE rwd.emp_id = e.emp_id
              AND rwd.roster_date <= ds.work_date
            ORDER BY rwd.roster_date DESC
            LIMIT 1
        ) AS shift_id
    FROM date_spine ds
    CROSS JOIN (SELECT DISTINCT emp_id FROM staging__employees) e
),

-- ── STEP 2: shift metadata ────────────────────────────────────────────────────
shift_meta AS (
    SELECT
        shift_id,
        shift_name,
        start_time,   -- e.g. '22:00' for night
        end_time,     -- e.g. '06:00' next day
        crosses_midnight  -- boolean: 1 if night shift
    FROM staging__shifts
),

-- ── STEP 3: holidays ─────────────────────────────────────────────────────────
holiday_dates AS (
    SELECT holiday_date AS h_date
    FROM staging__holidays
),

-- ── STEP 4: approved leave days ───────────────────────────────────────────────
approved_leave AS (
    SELECT emp_id, leave_date
    FROM staging__leave_days
),

-- ── STEP 5: assign shift_start_ts and shift_end_ts ────────────────────────────
scheduled AS (
    SELECT
        rf.work_date,
        rf.emp_id,
        rf.shift_id,
        sm.shift_name,
        sm.start_time,
        sm.end_time,
        sm.crosses_midnight,
        -- Build full timestamps for shift boundaries
        DATETIME(rf.work_date || ' ' || sm.start_time) AS shift_start_ts,
        CASE
            WHEN sm.crosses_midnight = '1' OR sm.crosses_midnight = 1
            THEN DATETIME(DATE(rf.work_date, '+1 day') || ' ' || sm.end_time)
            ELSE DATETIME(rf.work_date || ' ' || sm.end_time)
        END AS shift_end_ts
    FROM roster_filled rf
    LEFT JOIN shift_meta sm ON sm.shift_id = rf.shift_id
    WHERE rf.shift_id IS NOT NULL
),

-- ── STEP 6: pair punches — first IN and last OUT per employee per shift date ──
-- Night shift rule: punch belongs to shift-start date, not calendar date.
-- We shift the punch time back 6 hours to assign it to the correct date.
punches_dated AS (
    SELECT
        p.emp_id,
        p.punch_ts,
        p.punch_type,
        -- For night shifts we need the shift's start date.
        -- We use the rule: if punch hour < 06:00, it likely belongs to previous day's night shift.
        -- More precise: join shift roster to determine. Simple heuristic here:
        DATE(
            CASE
                WHEN CAST(STRFTIME('%H', p.punch_ts) AS INTEGER) < 6
                THEN DATETIME(p.punch_ts, '-6 hours')
                ELSE p.punch_ts
            END
        ) AS shift_date
    FROM staging__punches_clean p
),
punch_pairs AS (
    SELECT
        emp_id,
        shift_date,
        MIN(CASE WHEN UPPER(punch_type) IN ('IN','CHECK_IN','CI') THEN punch_ts END) AS first_in,
        MAX(CASE WHEN UPPER(punch_type) IN ('OUT','CHECK_OUT','CO') THEN punch_ts END) AS last_out
    FROM punches_dated
    GROUP BY emp_id, shift_date
),

-- ── STEP 7: compute metrics ───────────────────────────────────────────────────
metrics AS (
    SELECT
        s.work_date,
        s.emp_id,
        s.shift_id,
        s.shift_name,
        s.shift_start_ts,
        s.shift_end_ts,
        pp.first_in,
        pp.last_out,
        -- Worked minutes (NULL if missing punch)
        CASE
            WHEN pp.first_in IS NOT NULL AND pp.last_out IS NOT NULL
            THEN ROUND((JULIANDAY(pp.last_out) - JULIANDAY(pp.first_in)) * 24 * 60, 0)
            ELSE NULL
        END AS worked_minutes,
        -- Late minutes (only on Present days)
        CASE
            WHEN pp.first_in IS NOT NULL
                 AND JULIANDAY(pp.first_in) > JULIANDAY(s.shift_start_ts) + (10.0 / 1440)
            THEN ROUND((JULIANDAY(pp.first_in) - JULIANDAY(s.shift_start_ts)) * 1440, 0)
            ELSE 0
        END AS late_minutes,
        -- Early departure minutes
        CASE
            WHEN pp.last_out IS NOT NULL
                 AND JULIANDAY(pp.last_out) < JULIANDAY(s.shift_end_ts) - (10.0 / 1440)
            THEN ROUND((JULIANDAY(s.shift_end_ts) - JULIANDAY(pp.last_out)) * 1440, 0)
            ELSE 0
        END AS early_departure_minutes,
        -- OT minutes (after shift end, rounded to whole 30-min blocks)
        CASE
            WHEN pp.last_out IS NOT NULL
                 AND JULIANDAY(pp.last_out) > JULIANDAY(s.shift_end_ts)
            THEN (CAST(
                    ROUND((JULIANDAY(pp.last_out) - JULIANDAY(s.shift_end_ts)) * 1440, 0)
                  AS INTEGER) / 30) * 30
            ELSE 0
        END AS ot_minutes_from_punches,
        -- Is Sunday?
        CASE WHEN STRFTIME('%w', s.work_date) = '0' THEN 1 ELSE 0 END AS is_sunday,
        -- Is holiday?
        CASE WHEN hd.h_date IS NOT NULL THEN 1 ELSE 0 END AS is_holiday,
        -- Is on approved leave?
        CASE WHEN al.leave_date IS NOT NULL THEN 1 ELSE 0 END AS is_on_leave
    FROM scheduled s
    LEFT JOIN punch_pairs pp
           ON pp.emp_id = s.emp_id AND pp.shift_date = s.work_date
    LEFT JOIN holiday_dates hd ON hd.h_date = s.work_date
    LEFT JOIN approved_leave al
           ON al.emp_id = s.emp_id AND al.leave_date = s.work_date
),

-- ── STEP 8: Sunday / Holiday OT override ──────────────────────────────────────
ot_adjusted AS (
    SELECT
        *,
        CASE
            WHEN (is_sunday = 1 OR is_holiday = 1) AND worked_minutes IS NOT NULL
            THEN worked_minutes  -- all worked time is OT
            ELSE ot_minutes_from_punches
        END AS ot_minutes_final
    FROM metrics
),

-- ── STEP 9: status assignment (priority order) ───────────────────────────────
final AS (
    SELECT
        work_date,
        emp_id,
        shift_id,
        shift_name,
        shift_start_ts,
        shift_end_ts,
        first_in,
        last_out,
        worked_minutes,
        ROUND(worked_minutes / 60.0, 2)                  AS worked_hours,
        late_minutes,
        early_departure_minutes,
        ROUND(ot_minutes_final / 60.0, 2)                AS ot_hours_from_punches,
        CASE
            WHEN is_holiday = 1                          THEN 'Holiday'
            WHEN is_sunday  = 1                          THEN 'Weekly Off'
            WHEN is_on_leave = 1                         THEN 'On Leave'
            WHEN first_in IS NOT NULL
                 AND last_out IS NOT NULL                 THEN 'Present'
            WHEN first_in IS NOT NULL
                 OR  last_out IS NOT NULL                 THEN 'Missing Punch'
            ELSE                                              'Absent'
        END AS attendance_status
    FROM ot_adjusted
)

-- ── OUTPUT ────────────────────────────────────────────────────────────────────
SELECT * FROM final
ORDER BY emp_id, work_date;
