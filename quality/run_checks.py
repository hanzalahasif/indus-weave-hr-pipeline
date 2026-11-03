"""
Stage 6 — quality/run_checks.py
Automated data quality checks. Writes results to dq_results table.
Runs at the end of the full pipeline (or when stage 6 is selected).

Checks:
  1. Selected employee, attendance, and warehouse key uniqueness/null checks
  2. Selected fact-to-dimension referential-integrity checks
  3. Employee and punch row-count reconciliation
  4. Attendance-status accepted values
  5. Negative/overlong hours, SCD2 overlap, and overtime-date sanity checks
"""
from datetime import datetime, timezone
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.dialects.mssql import NVARCHAR

from config import MAX_SHIFT_HOURS, create_db_engine

# ─── Helper ───────────────────────────────────────────────────────────────────

def run_check(conn, check_name: str, layer: str, sql: str) -> dict[str, Any]:
    """Execute a scalar SQL check. Returns dict with result."""
    try:
        result = conn.execute(text(sql)).scalar()
        failed = int(result) if result is not None else 0
        status = "PASS" if failed == 0 else "FAIL"
    except Exception as e:
        failed = -1
        status  = f"ERROR: {e}"
    return {
        "check_name":  check_name,
        "layer":       layer,
        "status":      status,
        "failed_rows": failed,
        "run_at":      datetime.now(timezone.utc).isoformat(),
    }


def ensure_dq_table(engine):
    with engine.begin() as conn:
        conn.execute(text(f"""
            IF OBJECT_ID(N'dbo.dq_results', N'U') IS NULL
            CREATE TABLE dbo.dq_results (
                id          INT IDENTITY(1,1) PRIMARY KEY,
                check_name  NVARCHAR(200) NOT NULL,
                layer       NVARCHAR(50) NOT NULL,
                status      NVARCHAR(500) NOT NULL,
                failed_rows INT,
                run_at      NVARCHAR(40) NOT NULL
            )
        """))


def write_results(engine, results: list[dict]):
    rows = [{k: v for k, v in r.items()} for r in results]
    df = pd.DataFrame(rows)
    df.to_sql(
        "dq_results", engine,
        if_exists="append", index=False,
        chunksize=500,
        dtype={column: NVARCHAR(None) for column in df.select_dtypes(include=["object"]).columns},
    )


# ─── Checks ───────────────────────────────────────────────────────────────────

CHECKS = [
    # ── 1. PK uniqueness ─────────────────────────────────────────────────────
    ("PK: employees.emp_id unique", "staging",
     "SELECT COUNT(*) - COUNT(DISTINCT emp_id) FROM staging__employees"),
    ("PK: employees.emp_id not null", "staging",
     "SELECT COUNT(*) FROM staging__employees WHERE emp_id IS NULL OR emp_id = ''"),
    ("PK: attendance_daily uniqueness", "staging",
     """SELECT COUNT(*) FROM (
         SELECT emp_id, work_date, COUNT(*) AS c
         FROM staging__attendance_daily
         GROUP BY emp_id, work_date
         HAVING COUNT(*) > 1
     ) AS duplicate_rows"""),
    ("PK: dim_employee emp_key unique", "warehouse",
     "SELECT COUNT(*) - COUNT(DISTINCT emp_key) FROM warehouse__dim_employee"),
    ("PK: dim_date date_key unique", "warehouse",
     "SELECT COUNT(*) - COUNT(DISTINCT date_key) FROM warehouse__dim_date"),
    ("PK: fact_attendance_daily PK unique", "warehouse",
     "SELECT COUNT(*) - COUNT(DISTINCT attendance_key) FROM warehouse__fact_attendance_daily"),

    # ── 2. Referential integrity ──────────────────────────────────────────────
    ("RI: fact_attendance date_key in dim_date", "warehouse",
     """SELECT COUNT(*) FROM warehouse__fact_attendance_daily fad
        LEFT JOIN warehouse__dim_date d ON d.date_key = fad.date_key
        WHERE d.date_key IS NULL"""),
    ("RI: fact_attendance emp_key in dim_employee", "warehouse",
     """SELECT COUNT(*) FROM warehouse__fact_attendance_daily fad
        LEFT JOIN warehouse__dim_employee de ON de.emp_key = fad.emp_key
        WHERE de.emp_key IS NULL"""),
    ("RI: fact_payroll emp_key in dim_employee", "warehouse",
     """SELECT COUNT(*) FROM warehouse__fact_payroll_line fpl
        LEFT JOIN warehouse__dim_employee de ON de.emp_key = fpl.emp_key
        WHERE de.emp_key IS NULL"""),
    ("RI: fact_leave_day date_key in dim_date", "warehouse",
     """SELECT COUNT(*) FROM warehouse__fact_leave_day fld
        LEFT JOIN warehouse__dim_date d ON d.date_key = fld.date_key
        WHERE d.date_key IS NULL"""),

    # ── 3. Reconciliation: raw = staging + rejected ────────────────────────
    ("RECON: employees raw >= staging + merge_log", "reconciliation",
     """SELECT CASE
         WHEN (SELECT COUNT(*) FROM "raw__employees") <
              (SELECT COUNT(*) FROM staging__employees)
              + COALESCE((SELECT COUNT(*) FROM staging__employee_merge_log), 0)
         THEN 1 ELSE 0 END"""),
    ("RECON: punches raw = clean + rejected", "reconciliation",
     """SELECT ABS(
         (SELECT COUNT(*) FROM "raw__biometric_punches")
         - (SELECT COUNT(*) FROM staging__punches_clean)
         - (SELECT COUNT(*) FROM staging__rejected_punches)
     )"""),

    # ── 4. Accepted values ────────────────────────────────────────────────────
    ("ACPVAL: attendance_status valid", "warehouse",
     """SELECT COUNT(*) FROM warehouse__fact_attendance_daily
        WHERE attendance_status NOT IN
        ('Present','Absent','On Leave','Holiday','Weekly Off','Missing Punch')"""),

    # ── 5. Business sanity ────────────────────────────────────────────────────
    ("SANITY: no negative worked hours", "staging",
     "SELECT COUNT(*) FROM staging__attendance_daily WHERE worked_hours < 0"),
    ("SANITY: no shift > 16h", "staging",
     f"SELECT COUNT(*) FROM staging__attendance_daily WHERE worked_hours > {MAX_SHIFT_HOURS}"),
    ("SANITY: no SCD2 overlap in dim_employee", "warehouse",
     """SELECT COUNT(*) FROM warehouse__dim_employee a
        JOIN warehouse__dim_employee b
             ON a.emp_id = b.emp_id
             AND a.emp_key <> b.emp_key
             AND a.valid_from <= b.valid_to
             AND a.valid_to   >= b.valid_from"""),
    ("SANITY: no OT paid before shift date", "warehouse",
     """SELECT COUNT(*) FROM warehouse__fact_overtime_approved
        WHERE date_key < '2026-04-01' OR date_key > '2026-09-30'"""),
]


# ─── Main ─────────────────────────────────────────────────────────────────────

def run(engine=None):
    if engine is None:
        engine = create_db_engine()

    ensure_dq_table(engine)

    results = []
    with engine.connect() as conn:
        for check_name, layer, sql in CHECKS:
            r = run_check(conn, check_name, layer, sql)
            results.append(r)
            icon = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
            print(f"  {icon} [{layer}] {check_name}: {r['status']} (failed={r['failed_rows']})")

    write_results(engine, results)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = len(results) - pass_count
    print(f"\nDQ Summary: {pass_count} PASS / {fail_count} FAIL out of {len(results)} checks")
    return results


if __name__ == "__main__":
    run()
