"""Project paths, SQL Server connection, and pipeline settings."""
import os
from pathlib import Path
from urllib.parse import quote_plus

from sqlalchemy import create_engine

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "raw"

SQL_SERVER = os.environ.get("SQL_SERVER", r"DESKTOP-LNP0AFF\SQLEXPRESS")
SQL_DATABASE = os.environ.get("SQL_DATABASE", "indus_weave")
ODBC_DRIVER = os.environ.get("ODBC_DRIVER", "ODBC Driver 18 for SQL Server")
ODBC_CONNECTION = (
    f"DRIVER={{{ODBC_DRIVER}}};"
    f"SERVER={SQL_SERVER};"
    f"DATABASE={SQL_DATABASE};"
    "Trusted_Connection=yes;"
    "TrustServerCertificate=yes;"
)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"mssql+pyodbc:///?odbc_connect={quote_plus(ODBC_CONNECTION)}",
)


def create_db_engine():
    return create_engine(DATABASE_URL, fast_executemany=True)


RAW_FILES = {
    "employees": DATA_DIR / "employees.csv",
    "employment_history": DATA_DIR / "employment_history.csv",
    "departments": DATA_DIR / "departments.csv",
    "shifts": DATA_DIR / "shifts.json",
    "shift_roster": DATA_DIR / "shift_roster.csv",
    "device_mapping": DATA_DIR / "device_mapping.csv",
    "biometric_punches": DATA_DIR / "biometric_punches.csv",
    "holidays": DATA_DIR / "holidays.csv",
    "leave_requests": DATA_DIR / "leave_requests.json",
    "overtime_requests": DATA_DIR / "overtime_requests.csv",
    "payroll_lines": DATA_DIR / "payroll_lines.csv",
    "applications": DATA_DIR / "applications.csv",
}

LATE_THRESHOLD_MIN = 10
EARLY_DEPARTURE_MIN = 10
DUPLICATE_PUNCH_WINDOW_S = 120
MAX_SHIFT_HOURS = 16
OT_HALF_HOUR_BLOCK = 30

PERIOD_START = "2026-04-01"
PERIOD_END = "2026-09-30"
