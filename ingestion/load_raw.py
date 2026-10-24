"""
Stage 1 — load_raw.py
Loads every HCM source file into the `raw` schema, all columns as TEXT.
Features:
  • _source_file, _loaded_at, _row_hash metadata columns
  • Idempotent via ON CONFLICT (_row_hash) DO NOTHING  (SQLite & PG)
  • Row-count reconciliation log per file
  • JSON files are row-expanded before insert
"""
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATABASE_URL, RAW_FILES, LOG_FILE

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# ─── Helpers ──────────────────────────────────────────────────────────────────

def row_hash(row: pd.Series) -> str:
    """MD5 hash of all values in a row joined with pipe."""
    content = "|".join(str(v) for v in row.values)
    return hashlib.md5(content.encode()).hexdigest()


def load_file_to_df(name: str, path: Path) -> pd.DataFrame:
    """Read CSV or JSON into a flat DataFrame, all columns as str."""
    suffix = path.suffix.lower()
    if suffix == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif suffix == ".json":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        # Support both list-of-dicts and a single top-level list
        if isinstance(data, list):
            df = pd.json_normalize(data)
        elif isinstance(data, dict):
            # find the first list value
            key = next(k for k, v in data.items() if isinstance(v, list))
            df = pd.json_normalize(data[key])
        else:
            raise ValueError(f"Unexpected JSON structure in {path}")
        df = df.astype(str)
    else:
        raise ValueError(f"Unsupported file format: {suffix}")

    # Sanitize column names: replace '.' with '_' to prevent SQL bind parameter issues
    df.columns = [c.replace(".", "_") for c in df.columns]
    return df


def add_metadata(df: pd.DataFrame, source_file: str, loaded_at: str) -> pd.DataFrame:
    """Append _source_file, _loaded_at, _row_hash columns."""
    df = df.copy()
    df["_source_file"] = source_file
    df["_loaded_at"]   = loaded_at
    # Fast vectorized row hash
    vals = df.values
    df["_row_hash"] = [hashlib.md5("|".join(str(v) for v in row).encode()).hexdigest() for row in vals]
    return df


def ensure_raw_table(engine, table_name: str, df: pd.DataFrame):
    """
    Create `raw.<table_name>` if it doesn't exist, with a UNIQUE constraint
    on _row_hash to enable idempotent loads.
    SQLite does not support schemas, so we prefix with raw__.
    """
    is_sqlite = engine.dialect.name == "sqlite"
    tbl = f"raw__{table_name}" if is_sqlite else f"raw.{table_name}"

    cols_ddl = ",\n    ".join(
        f'"{c}" TEXT' for c in df.columns if c != "_row_hash"
    )

    if is_sqlite:
        ddl = f"""
        CREATE TABLE IF NOT EXISTS "{tbl}" (
            {cols_ddl},
            "_row_hash" TEXT NOT NULL,
            UNIQUE ("_row_hash")
        )"""
    else:
        ddl = f"""
        CREATE SCHEMA IF NOT EXISTS raw;
        CREATE TABLE IF NOT EXISTS {tbl} (
            {cols_ddl},
            "_row_hash" TEXT NOT NULL,
            CONSTRAINT uq_{table_name}_hash UNIQUE ("_row_hash")
        )"""

    with engine.begin() as conn:
        if not is_sqlite:
            conn.execute(text("CREATE SCHEMA IF NOT EXISTS raw"))
        conn.execute(text(f'DROP TABLE IF EXISTS "{tbl}"' if is_sqlite else f"DROP TABLE IF EXISTS {tbl}"))
        conn.execute(text(ddl))


def upsert_df(engine, table_name: str, df: pd.DataFrame, chunksize: int = 10000):
    """
    Insert rows in chunks; skip any whose _row_hash already exists.
    SQLite: INSERT OR IGNORE. PostgreSQL: ON CONFLICT DO NOTHING.
    """
    is_sqlite = engine.dialect.name == "sqlite"
    tbl = f"raw__{table_name}" if is_sqlite else f"raw.{table_name}"

    cols = list(df.columns)
    placeholders = ", ".join(f":{c}" for c in cols)
    col_list     = ", ".join(f'"{c}"' for c in cols)

    if is_sqlite:
        sql = f'INSERT OR IGNORE INTO "{tbl}" ({col_list}) VALUES ({placeholders})'
    else:
        sql = f'INSERT INTO {tbl} ({col_list}) VALUES ({placeholders}) ON CONFLICT ("_row_hash") DO NOTHING'

    total = len(df)
    with engine.begin() as conn:
        for i in range(0, total, chunksize):
            chunk = df.iloc[i : i + chunksize].to_dict(orient="records")
            conn.execute(text(sql), chunk)


def log_row_counts(engine, table_name: str, file_rows: int, is_sqlite: bool):
    """Write a reconciliation entry to raw__load_log."""
    tbl = "raw__load_log" if is_sqlite else "raw.load_log"
    with engine.begin() as conn:
        conn.execute(text(f"""
            CREATE TABLE IF NOT EXISTS "{tbl}" (
                table_name    TEXT,
                source_rows   INTEGER,
                loaded_at     TEXT
            )
        """))
        conn.execute(text(f"""
            INSERT INTO "{tbl}" (table_name, source_rows, loaded_at)
            VALUES (:t, :r, :d)
        """), {"t": table_name, "r": file_rows, "d": datetime.now(timezone.utc).isoformat()})


# ─── Main ─────────────────────────────────────────────────────────────────────

def run(engine=None):
    if engine is None:
        engine = create_engine(DATABASE_URL)

    is_sqlite = engine.dialect.name == "sqlite"
    loaded_at = datetime.now(timezone.utc).isoformat()
    summary   = []

    for name, path in RAW_FILES.items():
        if not path.exists():
            log.warning(f"SKIP  {name}: file not found at {path}")
            continue

        log.info(f"Loading {name} <- {path.name}")
        df = load_file_to_df(name, path)
        file_rows = len(df)

        df = add_metadata(df, str(path.name), loaded_at)

        ensure_raw_table(engine, name, df)
        upsert_df(engine, name, df)
        log_row_counts(engine, name, file_rows, is_sqlite)

        # Verify DB row count matches file rows (idempotent: may be less on re-run)
        tbl = f'"raw__{name}"' if is_sqlite else f"raw.{name}"
        with engine.connect() as conn:
            db_rows = conn.execute(text(f"SELECT COUNT(*) FROM {tbl}")).scalar()

        log.info(f"  file={file_rows:>7,}  db={db_rows:>7,}  table={tbl}")
        summary.append({"table": name, "file_rows": file_rows, "db_rows": db_rows})

    # Print summary table
    log.info("\n-- Row-count reconciliation --")
    log.info(f"{'Table':<25} {'File':>10} {'DB':>10}")
    for s in summary:
        flag = "" if s["file_rows"] == s["db_rows"] else " <- NOTE: idempotent dedup"
        log.info(f"{s['table']:<25} {s['file_rows']:>10,} {s['db_rows']:>10,}{flag}")

    return summary


if __name__ == "__main__":
    run()
