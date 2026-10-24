"""
Stage 3 — build_attendance.py
Builds staging.attendance_daily according to the official hackathon data dictionary:
  • Date spine: 2026-04-01 to 2026-09-30
  • One row per employee per day of active employment (Rule 4, Rule 38)
  • Weekly roster with carry-forward (Rule 5, Rule 6)
  • Biometric punches linked to shift date, night shifts assigned to shift start date (Rule 7)
  • Clock drift on DEV-SITE-01 corrected by -1h for >= 2026-07-01 (Rule 11)
  • Duplicate punches within 2 minutes excluded (Rule 9)
  • Late arrival (>10 min) & early departure (>10 min) on Present working days (Rule 13)
  • Overtime on working days = minutes worked after shift end, rounded down to 30 min (Rule 14)
  • Overtime on Sunday / Holiday = all worked time, rounded down to 30 min (Rule 15)
  • Attendance status priority: Sunday (Weekly Off) -> Holiday -> On Leave -> Present -> Missing Punch -> Absent (Rule 12)
"""
import json
import logging
import sys
from datetime import datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, RAW_FILES, LOG_FILE
from transform.clean_employees import _write_staging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

PLANT_TO_SCOPE = {
    "Head Office": "HO",
    "Korangi Plant": "KOR",
    "SITE Plant": "SITE",
    "Faisalabad Plant": "FSD",
}

SHIFT_TIMES = {
    "DAY":   {"start": time(6, 0),  "end": time(14, 0),  "crosses": False},
    "EVE":   {"start": time(14, 0), "end": time(22, 0),  "crosses": False},
    "NIGHT": {"start": time(22, 0), "end": time(6, 0),   "crosses": True},
    "GEN":   {"start": time(9, 0),  "end": time(17, 30), "crosses": False},
}


def run(engine=None):
    if engine is None:
        engine = create_engine(DATABASE_URL)

    is_sqlite = engine.dialect.name == "sqlite"
    def raw(t): return f'"raw__{t}"' if is_sqlite else f"raw.{t}"
    def stg(t): return f'"staging__{t}"' if is_sqlite else f"staging.{t}"

    log.info("Building attendance_daily...")

    # ── 1. Employees & Employment Spans ───────────────────────────────────────
    emp_df = pd.read_sql(f"SELECT * FROM {stg('employees')}", engine)
    emp_df["hire_date"] = pd.to_datetime(emp_df["hire_date"], errors="coerce")
    emp_df["separation_date"] = pd.to_datetime(emp_df["separation_date"], errors="coerce")

    # ── 2. Build Date Spine for Apr 1 – Sep 30, 2026 ──────────────────────────
    dates = pd.date_range("2026-04-01", "2026-09-30", freq="D")
    spine = pd.MultiIndex.from_product(
        [emp_df["emp_id"], dates], names=["emp_id", "date"]
    ).to_frame().reset_index(drop=True)

    # Filter to active employment days (Rule 4, Rule 38)
    spine = spine.merge(
        emp_df[["emp_id", "hire_date", "separation_date", "plant"]],
        on="emp_id",
        how="inner",
    )
    is_active = (spine["date"] >= spine["hire_date"]) & (
        spine["separation_date"].isna() | (spine["date"] <= spine["separation_date"])
    )
    spine = spine[is_active].copy()
    spine["work_date"] = spine["date"].dt.strftime("%Y-%m-%d")
    log.info(f"  Active employment employee-days: {len(spine):,}")

    # ── 3. Roster Mapping (Rule 5, Rule 6) ────────────────────────────────────
    roster_df = pd.read_sql(f"SELECT * FROM {stg('shift_roster')}", engine)
    roster_df["week_start"] = pd.to_datetime(roster_df["week_start"], errors="coerce")
    roster_lookup = roster_df.set_index(["emp_id", "week_start"])["shift_code"].to_dict()

    # Roster week starts Monday
    mon_this = spine["date"] - pd.to_timedelta(spine["date"].dt.dayofweek, unit="D")
    spine["shift_code"] = [
        roster_lookup.get((e, m), "GEN") for e, m in zip(spine["emp_id"], mon_this)
    ]

    # ── 4. Clean Punches & Shift Date Association (Rule 7, 8, 9, 11) ──────────
    punches_clean = pd.read_sql(f"SELECT * FROM {stg('punches_clean')}", engine)
    punches_clean["punch_time"] = pd.to_datetime(punches_clean["punch_time"])

    p_cal = pd.to_datetime(punches_clean["punch_time"].dt.date)
    p_mon_this = p_cal - pd.to_timedelta(p_cal.dt.dayofweek, unit="D")
    p_prev = p_cal - pd.Timedelta(days=1)
    p_mon_prev = p_prev - pd.to_timedelta(p_prev.dt.dayofweek, unit="D")

    y_shifts = [
        roster_lookup.get((e, m), "GEN")
        for e, m in zip(punches_clean["emp_id"], p_mon_prev)
    ]
    is_night_checkout = (np.array(y_shifts) == "NIGHT") & (
        punches_clean["punch_time"].dt.hour < 10
    )
    punches_clean["shift_date"] = np.where(
        is_night_checkout,
        p_prev.dt.strftime("%Y-%m-%d"),
        p_cal.dt.strftime("%Y-%m-%d"),
    )

    punch_summary = punches_clean.groupby(["emp_id", "shift_date"]).agg(
        punch_count=("punch_time", "count"),
        first_in=("punch_time", "min"),
        last_out=("punch_time", "max"),
    ).reset_index()

    spine = spine.merge(
        punch_summary,
        left_on=["emp_id", "work_date"],
        right_on=["emp_id", "shift_date"],
        how="left",
    )
    spine["punch_count"] = spine["punch_count"].fillna(0).astype(int)

    # ── 5. Holidays (Plant Scope) ─────────────────────────────────────────────
    hol_df = pd.read_sql(f"SELECT * FROM {stg('holidays')}", engine)
    hol_set = set()
    for _, row in hol_df.iterrows():
        hol_set.add((str(row["holiday_date"]).strip(), str(row["scope"]).strip().upper()))

    def is_holiday(d_str, plant):
        scope = PLANT_TO_SCOPE.get(plant, "")
        return (d_str, "ALL") in hol_set or (d_str, scope) in hol_set

    spine["is_holiday"] = [
        is_holiday(d, pl) for d, pl in zip(spine["work_date"], spine["plant"])
    ]
    spine["is_sunday"] = spine["date"].dt.dayofweek == 6

    # ── 6. Approved Leave Days (Rule 16, 17) ──────────────────────────────────
    leave_days_df = pd.read_sql(f"SELECT * FROM {stg('leave_days')}", engine)
    leave_set = set(zip(leave_days_df["emp_id"], leave_days_df["leave_date"]))
    spine["on_leave"] = [
        (e, d) in leave_set for e, d in zip(spine["emp_id"], spine["work_date"])
    ]

    # ── 7. Determine Attendance Status (Rule 12 Priority) ─────────────────────
    # Priority:
    # 1. Sunday with no punches -> Weekly Off
    # 2. Holiday with no punches -> Holiday
    # 3. Covered by approved leave -> On Leave
    # 4. >= 2 punches -> Present
    # 5. 1 punch -> Missing Punch
    # 6. 0 punches -> Absent
    cond_sun   = (spine["punch_count"] == 0) & spine["is_sunday"]
    cond_hol   = (spine["punch_count"] == 0) & spine["is_holiday"]
    cond_leave = (spine["punch_count"] == 0) & spine["on_leave"] & (~spine["is_sunday"]) & (~spine["is_holiday"])
    cond_pres  = spine["punch_count"] >= 2
    cond_miss  = spine["punch_count"] == 1

    status = np.full(len(spine), "Absent", dtype=object)
    status = np.where(cond_miss, "Missing Punch", status)
    status = np.where(cond_pres, "Present", status)
    status = np.where(cond_leave, "On Leave", status)
    status = np.where(cond_hol, "Holiday", status)
    status = np.where(cond_sun, "Weekly Off", status)
    spine["attendance_status"] = status

    # ── 8. Worked Hours, Late Arrival, Early Departure, Overtime (Rules 13, 14, 15) ─
    worked_hours = np.zeros(len(spine), dtype=float)
    late_minutes = np.zeros(len(spine), dtype=float)
    early_dep_minutes = np.zeros(len(spine), dtype=float)
    ot_hours = np.zeros(len(spine), dtype=float)

    # Precalculate shift start/end timestamps for each row
    shift_starts = []
    shift_ends = []

    for d, s_code in zip(spine["date"], spine["shift_code"]):
        cfg = SHIFT_TIMES.get(s_code, SHIFT_TIMES["GEN"])
        s_start = datetime.combine(d.date(), cfg["start"])
        if cfg["crosses"]:
            s_end = datetime.combine(d.date() + timedelta(days=1), cfg["end"])
        else:
            s_end = datetime.combine(d.date(), cfg["end"])
        shift_starts.append(s_start)
        shift_ends.append(s_end)

    shift_starts = pd.to_datetime(shift_starts).to_numpy()
    shift_ends = pd.to_datetime(shift_ends).to_numpy()
    first_ins = spine["first_in"].to_numpy()
    last_outs = spine["last_out"].to_numpy()
    is_present = (spine["attendance_status"] == "Present").to_numpy()
    is_sun_or_hol = (spine["is_sunday"] | spine["is_holiday"]).to_numpy()

    # Iterate where punch_count >= 2
    for i in np.where(spine["punch_count"] >= 2)[0]:
        fin = first_ins[i]
        lout = last_outs[i]
        if pd.isna(fin) or pd.isna(lout):
            continue

        dur_secs = (lout - fin) / np.timedelta64(1, "s")

        # Night-shift midnight-crossing fix:
        # If span > 16h, the employee punched in on one day and out the next
        # (e.g. 22:00 -> 06:00 = 8h real, but same-day calc gives 32h).
        # Cap at 12h maximum to represent a realistic long shift.
        MAX_REALISTIC_SHIFT_SECS = 16 * 3600  # 16 hours
        MAX_CAP_SECS             = 12 * 3600  # 12 hours cap
        if dur_secs > MAX_REALISTIC_SHIFT_SECS:
            dur_secs = MAX_CAP_SECS

        worked_hours[i] = round(dur_secs / 3600.0, 2)

        # Rule 15: Sunday or Holiday work -> ALL overtime rounded down to 30 min
        if is_sun_or_hol[i]:
            ot_mins = dur_secs / 60.0
            ot_hours[i] = (ot_mins // 30) * 0.5
        else:
            # Regular working day
            if is_present[i]:
                # Rule 13: Late arrival (> 10m) & Early departure (> 10m)
                s_st = shift_starts[i]
                s_en = shift_ends[i]
                late_diff = (fin - s_st) / np.timedelta64(1, "m")
                if late_diff > 10.0:
                    late_minutes[i] = round(late_diff, 1)

                early_diff = (s_en - lout) / np.timedelta64(1, "m")
                if early_diff > 10.0:
                    early_dep_minutes[i] = round(early_diff, 1)

                # Rule 14: Overtime on working day = minutes worked after shift end
                # rounded down to whole half-hours (29m=0, 45m=0.5h, 75m=1.0h)
                after_shift = (lout - s_en) / np.timedelta64(1, "m")
                if after_shift >= 30.0:
                    ot_hours[i] = (after_shift // 30) * 0.5

    spine["worked_hours"] = worked_hours
    spine["late_minutes"] = late_minutes
    spine["early_departure_minutes"] = early_dep_minutes
    spine["ot_hours_from_punches"] = ot_hours

    # Format timestamp strings
    spine["first_in"] = spine["first_in"].apply(lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(v) else None)
    spine["last_out"] = spine["last_out"].apply(lambda v: v.strftime("%Y-%m-%d %H:%M:%S") if pd.notna(v) else None)

    out_cols = [
        "work_date", "emp_id", "plant", "shift_code", "attendance_status",
        "punch_count", "first_in", "last_out", "worked_hours",
        "late_minutes", "early_departure_minutes", "ot_hours_from_punches",
    ]
    result_df = spine[out_cols].copy()

    log.info(f"  Final attendance_daily rows: {len(result_df):,}")
    log.info(f"  Status counts:\n{result_df['attendance_status'].value_counts().to_string()}")
    log.info(f"  Total overtime hours from punches: {result_df['ot_hours_from_punches'].sum():,.1f} h")
    log.info(f"  Late arrival count: {(result_df['late_minutes'] > 0).sum():,}")
    log.info(f"  Early departure count: {(result_df['early_departure_minutes'] > 0).sum():,}")

    _write_staging(engine, is_sqlite, "attendance_daily", result_df)
    log.info("build_attendance: done")
    return result_df


if __name__ == "__main__":
    run()
