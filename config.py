"""
config.py — Central configuration for Indus Weave HR Pipeline
All thresholds, paths, and DB settings live here.
"""
import os
from pathlib import Path

# ─── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).parent
DATA_DIR   = BASE_DIR / "data" / "raw"
LOG_DIR    = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

# ─── Database ─────────────────────────────────────────────────────────────────
# SQLite (default). To switch to PostgreSQL, set env var DATABASE_URL.
# e.g.  DATABASE_URL=postgresql+psycopg2://user:pass@localhost/indus_weave
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{BASE_DIR / 'indus_weave.db'}"
)

# ─── Raw source files ─────────────────────────────────────────────────────────
RAW_FILES = {
    "employees":            DATA_DIR / "employees.csv",
    "employment_history":   DATA_DIR / "employment_history.csv",
    "departments":          DATA_DIR / "departments.csv",
    "shifts":               DATA_DIR / "shifts.json",
    "shift_roster":         DATA_DIR / "shift_roster.csv",
    "device_mapping":       DATA_DIR / "device_mapping.csv",
    "biometric_punches":    DATA_DIR / "biometric_punches.csv",
    "holidays":             DATA_DIR / "holidays.csv",
    "leave_requests":       DATA_DIR / "leave_requests.json",
    "overtime_requests":    DATA_DIR / "overtime_requests.csv",
    "payroll_lines":        DATA_DIR / "payroll_lines.csv",
    "applications":         DATA_DIR / "applications.csv",
}

# ─── Business-rule thresholds ─────────────────────────────────────────────────
LATE_THRESHOLD_MIN        = 10    # minutes after shift start → Late
EARLY_DEPARTURE_MIN       = 10    # minutes before shift end  → Early departure
DUPLICATE_PUNCH_WINDOW_S  = 120   # seconds  → same employee = one punch
MAX_SHIFT_HOURS           = 16    # sanity cap for DQ checks
OT_HALF_HOUR_BLOCK        = 30    # round down to whole 30-min blocks
CLOCK_DRIFT_THRESHOLD_MIN = 45    # minutes — device whose avg offset > this is faulty

# ─── Period under analysis ────────────────────────────────────────────────────
PERIOD_START = "2026-04-01"
PERIOD_END   = "2026-09-30"

# ─── Leave entitlements (full year) ───────────────────────────────────────────
ANNUAL_LEAVE_ENTITLEMENT = 21    # days per year (for Q10)

# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_FILE = LOG_DIR / "pipeline.log"
