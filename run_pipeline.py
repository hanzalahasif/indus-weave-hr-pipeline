"""
run_pipeline.py — Master orchestrator (Bonus Task)
Rebuilds the entire pipeline from raw files with ONE command:
    python run_pipeline.py

Stages:
  1  load_raw         → raw schema
  2a clean_employees  → staging.employees, employee_merge_log
  2b clean_history    → staging.employment_history
  2c clean_punches    → staging.punches_clean, rejected_punches
  2d flatten_leave    → staging.leave_requests, approval_steps, leave_days
  2e clean_other      → staging.departments, shifts, roster, holidays, OT, payroll
  3  attendance_daily → staging.attendance_daily (SQL via Python)
  4  warehouse DDL    → warehouse dims + facts
  6  dq_checks        → dq_results table

Options:
  --reset    Drop and recreate the database before running (full rebuild)
  --stage N  Run only a specific stage (1, 2, 3, 4, 6)
"""
import argparse
import logging
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))
from config import DATABASE_URL, LOG_FILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def stage_banner(n: int, name: str):
    log.info(f"\n{'='*60}")
    log.info(f"  STAGE {n}: {name}")
    log.info(f"{'='*60}")


def run_sql_file(engine, path: Path):
    """Execute a .sql file statement by statement."""
    sql = path.read_text(encoding="utf-8")
    # Split on semicolons but keep them, skip empty
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def stage1(engine):
    stage_banner(1, "Ingest raw files")
    from ingestion.load_raw import run
    return run(engine)


def stage2(engine):
    stage_banner(2, "Clean & standardise staging")
    from transform.clean_employees import run as clean_emp
    from transform.clean_history   import run as clean_hist
    from transform.clean_punches   import run as clean_pun
    from transform.flatten_leave   import run as flat_leave

    clean_emp(engine)
    clean_hist(engine)
    clean_pun(engine)
    flat_leave(engine)

    # Clean remaining tables (departments, shifts, roster, holidays, OT, payroll)
    # These are simpler: trim text, fix dates, write to staging
    _clean_simple_tables(engine)


def _clean_simple_tables(engine):
    """
    For tables that don't need special logic, just copy raw -> staging
    with basic text cleanup (trim, ISO date normalisation).
    Tables: departments, shifts, shift_roster, holidays, overtime_requests, payroll_lines, device_mapping, applications
    """
    import pandas as pd
    from transform.clean_employees import _write_staging, parse_date

    is_sqlite = engine.dialect.name == "sqlite"
    simple = {
        "departments":       ["renamed_on"],
        "shifts":            [],
        "shift_roster":      ["week_start"],
        "holidays":          ["holiday_date"],
        "overtime_requests": ["ot_date"],
        "payroll_lines":     [],
        "device_mapping":    ["enrolled_on"],
        "applications":      ["stage_date"],
    }

    for tbl, date_cols in simple.items():
        raw_tbl = f'"raw__{tbl}"' if is_sqlite else f"raw.{tbl}"
        try:
            df = pd.read_sql(f"SELECT * FROM {raw_tbl}", engine)
        except Exception as e:
            log.warning(f"  Could not read {raw_tbl}: {e}")
            continue

        # Strip all text
        for col in df.columns:
            if not col.startswith("_"):
                df[col] = df[col].astype(str).str.strip()

        for dc in date_cols:
            if dc in df.columns:
                df[dc] = df[dc].apply(parse_date)

        _write_staging(engine, is_sqlite, tbl, df)


def stage3(engine):
    stage_banner(3, "Build attendance_daily (Python + Business Rules)")
    from transform.build_attendance import run as build_att
    return build_att(engine)


def stage4(engine):
    stage_banner(4, "Build warehouse (DDL + load)")
    ddl_dir = Path(__file__).parent / "warehouse" / "ddl"
    for fname in ["01_dims.sql", "02_facts.sql", "03_load_warehouse.sql"]:
        path = ddl_dir / fname
        if path.exists():
            log.info(f"  Executing {fname}")
            run_sql_file(engine, path)
        else:
            log.warning(f"  {fname} not found — skipping")


def stage6(engine):
    stage_banner(6, "Data quality checks")
    from quality.run_checks import run
    return run(engine)


def export_results(engine):
    """Save Q1–Q10 query results as CSVs in analytics/results/."""
    import pandas as pd

    is_sqlite = engine.dialect.name == "sqlite"
    results_dir = Path(__file__).parent / "analytics" / "results"
    results_dir.mkdir(exist_ok=True)

    sql_dir = Path(__file__).parent / "analytics"
    for q_file in sorted(sql_dir.glob("q*.sql")):
        sql = q_file.read_text(encoding="utf-8")
        try:
            with engine.connect() as conn:
                df = pd.read_sql(sql, conn)
            out_path = results_dir / q_file.name.replace(".sql", ".csv")
            df.to_csv(out_path, index=False)
            log.info(f"  Saved {out_path.name} ({len(df):,} rows)")
        except Exception as e:
            log.warning(f"  {q_file.name} failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Indus Weave HR Pipeline")
    parser.add_argument("--reset", action="store_true",
                        help="Drop and recreate the database")
    parser.add_argument("--stage", type=int, choices=[1, 2, 3, 4, 6],
                        help="Run only a specific stage")
    parser.add_argument("--export", action="store_true",
                        help="Export Q1-Q10 results to CSV after pipeline")
    args = parser.parse_args()

    engine = create_engine(DATABASE_URL)

    if args.reset and engine.dialect.name == "sqlite":
        db_path = DATABASE_URL.replace("sqlite:///", "")
        import os
        if os.path.exists(db_path):
            os.remove(db_path)
            log.info(f"Dropped SQLite database: {db_path}")
        engine = create_engine(DATABASE_URL)

    t0 = time.time()

    if args.stage:
        stages = {1: stage1, 2: stage2, 3: stage3, 4: stage4, 6: stage6}
        stages[args.stage](engine)
    else:
        # Full pipeline
        stage1(engine)
        stage2(engine)
        stage3(engine)
        stage4(engine)
        stage6(engine)

    if args.export or not args.stage:
        export_results(engine)

    elapsed = time.time() - t0
    log.info(f"\n{'='*60}")
    log.info(f"  Pipeline complete in {elapsed:.1f}s")
    log.info(f"{'='*60}")


if __name__ == "__main__":
    main()
