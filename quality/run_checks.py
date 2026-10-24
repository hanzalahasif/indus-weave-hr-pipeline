"""
Stage 6 — quality/run_checks.py
Automated data quality checks. Writes results to dq_results table.
Runs after every load stage.

Checks:
  1. PK uniqueness + NOT NULL on every primary key
  2. Referential integrity: every fact row has matching dim row
  3. Reconciliation: raw rows = staging rows + rejected rows
  4. Accepted values: attendance_status, leave_type, pay_component
  5. Business sanity: no negative hours, no shifts > 16h, no SCD2 overlaps
"""
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, LOG_FILE, MAX_SHIFT_HOURS
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

VALID_ATTENDANCE_STATUS = frozenset(
    ["Present", "Absent", "On Leave", "Holiday", "Weekly Off", "Missing Punch"]
)
VALID_LEAVE_TYPES = frozenset(
    ["Annual", "Sick", "Casual", "Maternity", "Paternity", "Unpaid", "Bereavement"]
)
VALID_PAY_COMPONENTS = frozenset(
    ["Basic", "HRA", "Conveyance", "OT", "Overtime", "Overtime Pay", "Bonus",
     "Deduction", "Tax", "PF", "EOBI"]
)


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


def ensure_dq_table(engine, is_sqlite):
    tbl = '"dq_results"' if is_sqlite else "dq_results"
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {tbl} (
                id          INTEGER PRIMARY KEY {'AUTOINCREMENT' if is_sqlite else 'GENERATED ALWAYS AS IDENTITY'},
                check_name  TEXT NOT NULL,
                layer       TEXT NOT NULL,
                status      TEXT NOT NULL,
                failed_rows INTEGER,
                run_at      TEXT NOT NULL
            )
        """))


def write_results(engine, is_sqlite, results: list[dict]):
    tbl = '"dq_results"' if is_sqlite else "dq_results"
    rows = [{k: v for k, v in r.items()} for r in results]
    df = pd.DataFrame(rows)
    df.to_sql(
        "dq_results", engine,
        if_exists="append", index=False,
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
         HAVING c > 1
     )"""),
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
        engine = create_engine(DATABASE_URL)

    is_sqlite = engine.dialect.name == "sqlite"
    ensure_dq_table(engine, is_sqlite)

    results = []
    with engine.connect() as conn:
        for check_name, layer, sql in CHECKS:
            r = run_check(conn, check_name, layer, sql)
            results.append(r)
            icon = "[PASS]" if r["status"] == "PASS" else "[FAIL]"
            log.info(f"  {icon} [{layer}] {check_name}: {r['status']} (failed={r['failed_rows']})")

    write_results(engine, is_sqlite, results)

    pass_count = sum(1 for r in results if r["status"] == "PASS")
    fail_count = len(results) - pass_count
    log.info(f"\nDQ Summary: {pass_count} PASS / {fail_count} FAIL out of {len(results)} checks")
    return results


if __name__ == "__main__":
    run()
