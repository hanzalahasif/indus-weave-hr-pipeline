"""
Stage 2b — clean_history.py
Cleans employment_history and rebuilds valid_from / valid_to:
  • Ignores effective_to from source (unreliable per business rules)
  • valid_to = next record's effective_from − 1 day, per employee
  • Last record per employee gets valid_to = '9999-12-31'
"""
import pandas as pd

from config import create_db_engine
from transform.clean_employees import parse_date, _write_staging

def run(engine=None):
    if engine is None:
        engine = create_db_engine()

    src_tbl = "raw__employment_history"

    df = pd.read_sql(f"SELECT * FROM {src_tbl}", engine)
    print(f"Employment history raw rows: {len(df):,}")

    # ── Clean text + dates ────────────────────────────────────────────────────
    for col in df.columns:
        if not col.startswith("_"):
            df[col] = df[col].astype(str).str.strip()

    date_cols = ["effective_from", "effective_to"]
    for col in date_cols:
        if col in df.columns:
            df[col] = df[col].apply(parse_date)

    # Title-case department
    for col in ["department", "department_name"]:
        if col in df.columns:
            df[col] = df[col].str.title().str.replace(r"\s+", " ", regex=True)

    # ── Rebuild SCD2 dates ────────────────────────────────────────────────────
    df["effective_from_dt"] = pd.to_datetime(df["effective_from"], errors="coerce")
    df.sort_values(["emp_id", "effective_from_dt"], inplace=True)

    # valid_to = next row's effective_from − 1 day, within same emp_id
    df["valid_from"] = df["effective_from"]
    df["valid_to"] = (
        df.groupby("emp_id")["effective_from_dt"]
          .shift(-1)
          .sub(pd.Timedelta(days=1))
          .dt.strftime("%Y-%m-%d")
          .fillna("9999-12-31")
    )

    df.drop(columns=["effective_to", "effective_from_dt"], inplace=True)
    print(f"  Rebuilt valid_from/valid_to for {df['emp_id'].nunique():,} employees")

    _write_staging(engine, "employment_history", df)
    print("clean_history: done")
    return df


if __name__ == "__main__":
    run()
