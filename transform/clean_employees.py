"""
Stage 2a — clean_employees.py
Cleans and deduplicates the employees table:
  • Trims whitespace, fixes casing, normalises dates → ISO YYYY-MM-DD
  • Deduplication: keep latest updated_at per emp_id; log merged rows
"""
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, LOG_FILE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# Possible date formats in the raw data
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%m/%d/%Y"]


def parse_date(val: str) -> str | None:
    """Try multiple formats; return ISO string or None."""
    if not val or val.strip() in ("", "None", "NaT", "nan"):
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(val.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    log.warning(f"  Cannot parse date: {val!r}")
    return val.strip()


def run(engine=None):
    if engine is None:
        engine = create_engine(DATABASE_URL)

    is_sqlite = engine.dialect.name == "sqlite"
    src_tbl = '"raw__employees"' if is_sqlite else "raw.employees"
    run_at  = datetime.now(timezone.utc).isoformat()

    # ── Read raw ──────────────────────────────────────────────────────────────
    df = pd.read_sql(f"SELECT * FROM {src_tbl}", engine)
    log.info(f"Employees raw rows: {len(df):,}")

    # ── Basic cleaning ────────────────────────────────────────────────────────
    text_cols = [c for c in df.columns if not c.startswith("_")]
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip()

    # Normalise department name (title case + collapse spaces)
    for col in ["department", "department_name"]:
        if col in df.columns:
            df[col] = df[col].str.title().str.replace(r"\s+", " ", regex=True)

    # Fix date columns (hire_date, separation_date, date_of_birth)
    date_cols = ["date_of_birth", "hire_date", "separation_date",
                 "date_of_joining", "date_of_separation", "contract_end_date"]
    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_date)

    # ── Deduplication ─────────────────────────────────────────────────────────
    # Sort descending by updated_at so first record is the keeper
    df["_upd_sort"] = pd.to_datetime(df.get("updated_at"), errors="coerce")
    df.sort_values("_upd_sort", ascending=False, inplace=True)

    # Identify duplicates before dropping
    is_dup = df.duplicated(subset=["emp_id"], keep="first")
    dupes  = df[is_dup].copy()

    merge_log = []
    if len(dupes):
        keeper = df[~is_dup].set_index("emp_id")["updated_at"]
        for _, row in dupes.iterrows():
            merge_log.append({
                "emp_id":        row.get("emp_id"),
                "kept_updated_at":    keeper.get(row.get("emp_id"), ""),
                "dropped_updated_at": row.get("updated_at", ""),
                "reason":        "Duplicate emp_id — kept latest updated_at",
                "logged_at":     run_at,
            })

    df_clean = df[~is_dup].drop(columns=["_upd_sort"])
    log.info(f"  After dedup: {len(df_clean):,} rows  (dropped {len(dupes):,} dupes)")

    # ── Write staging.employees ───────────────────────────────────────────────
    _write_staging(engine, is_sqlite, "employees", df_clean)

    # ── Write staging.employee_merge_log ─────────────────────────────────────
    if merge_log:
        df_log = pd.DataFrame(merge_log)
        _write_staging(engine, is_sqlite, "employee_merge_log", df_log)
        log.info(f"  Merge-log entries written: {len(df_log):,}")

    log.info("clean_employees: done")
    return df_clean


def _write_staging(engine, is_sqlite, table, df):
    schema_prefix = "" if is_sqlite else "staging."
    tbl = f'"staging__{table}"' if is_sqlite else f"staging.{table}"

    with engine.begin() as conn:
        if not is_sqlite:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS staging"))
        conn.execute(text(f"DROP TABLE IF EXISTS {tbl}"))

    df.to_sql(
        f"staging__{table}" if is_sqlite else table,
        engine,
        schema=None if is_sqlite else "staging",
        if_exists="replace",
        index=False,
    )
    log.info(f"  Written {len(df):,} rows -> {tbl}")


if __name__ == "__main__":
    run()
