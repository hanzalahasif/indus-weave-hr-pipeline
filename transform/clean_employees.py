"""
Stage 2a — clean_employees.py
Cleans and deduplicates the employees table:
  • Trims whitespace, fixes casing, normalises dates → ISO YYYY-MM-DD
  • Deduplication: keep latest updated_at per emp_id; log merged rows
"""
from datetime import datetime, timezone
import pandas as pd
from sqlalchemy.dialects.mssql import NVARCHAR

from config import create_db_engine

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
    print(f"Warning: cannot parse date {val!r}")
    return val.strip()


def run(engine=None):
    if engine is None:
        engine = create_db_engine()

    src_tbl = "raw__employees"
    run_at  = datetime.now(timezone.utc).isoformat()

    # ── Read raw ──────────────────────────────────────────────────────────────
    df = pd.read_sql(f"SELECT * FROM {src_tbl}", engine)
    print(f"Employees raw rows: {len(df):,}")

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
    print(f"  After dedup: {len(df_clean):,} rows (dropped {len(dupes):,} duplicates)")

    # ── Write staging.employees ───────────────────────────────────────────────
    _write_staging(engine, "employees", df_clean)

    # ── Write staging.employee_merge_log ─────────────────────────────────────
    df_log = pd.DataFrame(merge_log, columns=[
        "emp_id", "kept_updated_at", "dropped_updated_at", "reason", "logged_at"
    ])
    _write_staging(engine, "employee_merge_log", df_log)
    print(f"  Merge-log entries written: {len(df_log):,}")

    print("clean_employees: done")
    return df_clean


def _write_staging(engine, table, df):
    tbl = f"staging__{table}"
    df.to_sql(
        tbl,
        engine,
        if_exists="replace",
        index=False,
        chunksize=500,
        dtype={
            column: NVARCHAR(None)
            for column in df.select_dtypes(include=["object"]).columns
        },
    )
    print(f"  Written {len(df):,} rows -> dbo.{tbl}")


if __name__ == "__main__":
    run()
