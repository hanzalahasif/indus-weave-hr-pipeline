"""Load the CSV and JSON source files into SQL Server raw tables."""
import json

import pandas as pd
from sqlalchemy.dialects.mssql import NVARCHAR

from config import RAW_FILES, create_db_engine


def load_file(path):
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif path.suffix.lower() == ".json":
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = next(value for value in data.values() if isinstance(value, list))
        else:
            raise ValueError(f"Unsupported JSON structure: {path}")
        df = pd.json_normalize(records).fillna("").astype(str)
    else:
        raise ValueError(f"Unsupported file format: {path.suffix}")

    df.columns = [column.replace(".", "_") for column in df.columns]
    return df


def run(engine=None):
    if engine is None:
        engine = create_db_engine()

    summary = []
    for name, path in RAW_FILES.items():
        if not path.exists():
            raise FileNotFoundError(f"Required source file not found: {path}")

        df = load_file(path)
        df["_source_file"] = path.name
        table = f"raw__{name}"
        df.to_sql(
            table,
            engine,
            if_exists="replace",
            index=False,
            chunksize=500,
            dtype={column: NVARCHAR(None) for column in df.columns},
        )
        summary.append({"table": table, "file_rows": len(df)})
        print(f"Loaded {len(df):,} rows from {path.name} into dbo.{table}")

    return summary


if __name__ == "__main__":
    run()
