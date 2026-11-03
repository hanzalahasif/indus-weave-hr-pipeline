"""
run_pipeline.py — Master orchestrator (Bonus Task)
Rebuilds the entire pipeline from raw files with ONE command:
    python run_pipeline.py

Stages:
  1  load_raw         → dbo.raw__* source tables
  2  clean/transform  → dbo.staging__* tables
  3  build_attendance → dbo.staging__attendance_daily (pandas)
  4  warehouse DDL    → warehouse dims + facts
  6  dq_checks        → dq_results table

Options:
  --reset    Drop pipeline tables before rebuilding them
  --stage N  Run only a specific stage (1, 2, 3, 4, 6)
"""
import argparse
import time
from pathlib import Path

from sqlalchemy import text

from config import RAW_FILES, create_db_engine


def stage_banner(n: int, name: str):
    print(f"\n{'='*60}")
    print(f"  STAGE {n}: {name}")
    print(f"{'='*60}")


def run_sql_file(engine, path: Path):
    """Run a complete SQL Server batch so CTEs stay attached to their statements."""
    sql = path.read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.exec_driver_sql(sql)


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
        raw_tbl = f"raw__{tbl}"
        df = pd.read_sql(f"SELECT * FROM {raw_tbl}", engine)

        # Strip all text
        for col in df.columns:
            if not col.startswith("_"):
                df[col] = df[col].astype(str).str.strip()

        for dc in date_cols:
            if dc in df.columns:
                df[dc] = df[dc].apply(parse_date)

        _write_staging(engine, tbl, df)


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
            print(f"  Executing {fname}")
            run_sql_file(engine, path)
        else:
            print(f"Error: required SQL file not found: {path}")
            raise FileNotFoundError(path)


def stage6(engine):
    stage_banner(6, "Data quality checks")
    from quality.run_checks import run
    return run(engine)


def export_results(engine):
    """Save Q1–Q10 query results as CSVs in analytics/results/."""
    import pandas as pd

    results_dir = Path(__file__).parent / "analytics" / "results"
    results_dir.mkdir(exist_ok=True)

    sql_dir = Path(__file__).parent / "analytics"
    for q_file in sorted(sql_dir.glob("q*.sql")):
        sql = q_file.read_text(encoding="utf-8")
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn)
        out_path = results_dir / q_file.name.replace(".sql", ".csv")
        df.to_csv(out_path, index=False)
        print(f"  Saved {out_path.name} ({len(df):,} rows)")


def reset_tables(engine):
    """Drop this pipeline's tables in foreign-key-safe order."""
    tables = [
        "warehouse__fact_attendance_daily",
        "warehouse__fact_leave_day",
        "warehouse__fact_overtime_approved",
        "warehouse__fact_payroll_line",
        "warehouse__dim_employee",
        "warehouse__dim_shift",
        "warehouse__dim_department",
        "warehouse__dim_date",
        "dq_results",
        "staging__attendance_daily",
        "staging__employee_merge_log",
        "staging__employees",
        "staging__employment_history",
        "staging__punches_clean",
        "staging__rejected_punches",
        "staging__leave_requests",
        "staging__leave_approval_steps",
        "staging__leave_days",
        "staging__departments",
        "staging__shifts",
        "staging__shift_roster",
        "staging__holidays",
        "staging__overtime_requests",
        "staging__payroll_lines",
        "staging__device_mapping",
        "staging__applications",
        *(f"raw__{name}" for name in RAW_FILES),
    ]
    with engine.begin() as conn:
        for table in tables:
            conn.execute(text(f"DROP TABLE IF EXISTS dbo.{table}"))


def main():
    parser = argparse.ArgumentParser(description="Indus Weave HR Pipeline")
    parser.add_argument("--reset", action="store_true",
                        help="Drop pipeline tables before rebuilding them")
    parser.add_argument("--stage", type=int, choices=[1, 2, 3, 4, 6],
                        help="Run only a specific stage")
    parser.add_argument("--export", action="store_true",
                        help="Export Q1-Q10 results to CSV after pipeline")
    args = parser.parse_args()

    engine = create_db_engine()

    if args.reset:
        reset_tables(engine)
        print("Dropped existing pipeline tables.")

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
    print(f"\n{'='*60}")
    print(f"  Pipeline complete in {elapsed:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
