"""
Stage 2c — clean_punches.py
Pipeline for biometric_punches:
  1. Map device_user_id -> emp_id via device_mapping; park unknowns in rejected_punches
  2. Detect faulty device (DEV-SITE-01 clock jumped +1 hr forward on 2026-07-01)
  3. Correct faulty device timestamps (-1 hour after 2026-07-01)
  4. Remove duplicate punches within 2-minute window per employee
  5. Write staging.punches_clean and staging.rejected_punches
"""
import pandas as pd

from config import DUPLICATE_PUNCH_WINDOW_S, create_db_engine
from transform.clean_employees import _write_staging

def run(engine=None):
    if engine is None:
        engine = create_db_engine()

    def raw(t): return f"raw__{t}"
    punches = pd.read_sql(f"SELECT * FROM {raw('biometric_punches')}", engine)
    mapping = pd.read_sql(f"SELECT * FROM {raw('device_mapping')}", engine)

    print(f"Raw punches: {len(punches):,}")

    # Standardise column names
    mapping = mapping.rename(columns=lambda c: c.strip())
    mapping["device_user_id"] = mapping["device_user_id"].astype(str).str.strip()
    mapping["emp_id"]         = mapping["emp_id"].astype(str).str.strip()
    mapping["device_id"]      = mapping["device_id"].astype(str).str.strip()

    punches = punches.rename(columns=lambda c: c.strip())
    time_col = "punch_time" if "punch_time" in punches.columns else "punch_ts"
    punches["device_user_id"] = punches["device_user_id"].astype(str).str.strip()
    punches["device_id"]      = punches["device_id"].astype(str).str.strip()
    punches["punch_time"]     = pd.to_datetime(punches[time_col], errors="coerce")

    # ── 1. Map device_user_id -> emp_id ───────────────────────────────────────
    merged = punches.merge(
        mapping[["device_user_id", "device_id", "emp_id"]],
        on=["device_user_id", "device_id"],
        how="left",
    )

    rejected = merged[merged["emp_id"].isna()].copy()
    rejected["reject_reason"] = "Unmapped device user (contractor/visitor)"
    clean    = merged[merged["emp_id"].notna()].copy()

    print(f"  Mapped: {len(clean):,}; rejected (unmapped): {len(rejected):,}")

    # ── 2. Detect & correct faulty device (DEV-SITE-01 clock jump) ────────────
    # DEV-SITE-01 clock jumped forward by +1 hr on 2026-07-01 00:00:00
    clean["clock_corrected"] = 0
    drift_mask = (clean["device_id"] == "DEV-SITE-01") & (clean["punch_time"] >= "2026-07-01")
    drift_count = drift_mask.sum()
    if drift_count > 0:
        clean.loc[drift_mask, "punch_time"] = clean.loc[drift_mask, "punch_time"] - pd.Timedelta(hours=1)
        clean.loc[drift_mask, "clock_corrected"] = 1
        print(f"  Corrected {drift_count:,} punches from faulty device DEV-SITE-01.")

    # ── 3. Remove duplicate punches (2-minute rule) ───────────────────────────
    clean.sort_values(["emp_id", "punch_time"], inplace=True)
    clean["prev_ts"]  = clean.groupby("emp_id")["punch_time"].shift(1)
    clean["gap_secs"] = (clean["punch_time"] - clean["prev_ts"]).dt.total_seconds()
    is_dup = (clean["gap_secs"] <= DUPLICATE_PUNCH_WINDOW_S) & clean["gap_secs"].notna()
    dup_punches = clean[is_dup].copy()
    dup_punches["reject_reason"] = "Duplicate punch within 2-minute window"

    clean_dedup = clean[~is_dup].drop(columns=["prev_ts", "gap_secs"])
    print(f"  After 2-minute dedup: {len(clean_dedup):,} punches (removed {is_dup.sum():,})")

    dup_rejected = dup_punches.drop(columns=["prev_ts", "gap_secs"])
    rejected_all = pd.concat([rejected, dup_rejected], ignore_index=True)

    # ── 4. Save formatted timestamps for staging ─────────────────────────────
    clean_dedup["punch_time"] = clean_dedup["punch_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    rejected_all["punch_time"] = rejected_all["punch_time"].astype(str)

    _write_staging(engine, "punches_clean", clean_dedup)
    _write_staging(engine, "rejected_punches", rejected_all)

    print("clean_punches: done")
    return clean_dedup, rejected_all


if __name__ == "__main__":
    run()
