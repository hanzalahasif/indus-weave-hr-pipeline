# Indus Weave HR Pipeline
**Developed & Engineered by Hanzalah Asif**  
*PeopleOps Data Hackathon — Oct 23–24, 2026*

---

## Author
| Name | Role |
|---|---|
| **Hanzalah Asif** | Data Engineer & Analytics Lead |

---

## Prerequisites
- Python 3.11+
- SQLite 3 (bundled with Python) **or** PostgreSQL 16+

```bash
pip install -r requirements.txt
```

---

## Quick start — rebuild from scratch

```bash
# 1. Put all 12 data files inside data/raw/
#    (employees.csv, employment_history.csv, … as listed below)

# 2. Full rebuild (drops and recreates the DB)
python run_pipeline.py --reset --export

# 3. Outputs:
#    indus_weave.db              ← SQLite database with all 4 schemas
#    analytics/results/q01.csv … q10.csv
#    logs/pipeline.log
```

To switch to PostgreSQL:
```bash
export DATABASE_URL="postgresql+psycopg2://user:pass@localhost/indus_weave"
python run_pipeline.py --reset --export
```

---

## Data files expected in `data/raw/`

| File | Rows | Format |
|---|---|---|
| employees.csv | ~1,316 | CSV |
| employment_history.csv | ~3,686 | CSV |
| departments.csv | ~25 | CSV |
| shifts.json | 4 | JSON |
| shift_roster.csv | ~36,402 | CSV |
| device_mapping.csv | ~1,260 | CSV |
| biometric_punches.csv | ~345,280 | CSV |
| holidays.csv | ~12 | CSV |
| leave_requests.json | ~5,372 | JSON |
| overtime_requests.csv | ~22,098 | CSV |
| payroll_lines.csv | ~53,617 | CSV |
| applications.csv | ~3,835 | CSV |

---

## Pipeline stages

```
Stage 1  load_raw.py            → raw__* tables (text, idempotent via _row_hash)
Stage 2a clean_employees.py     → staging__employees + employee_merge_log
Stage 2b clean_history.py       → staging__employment_history (SCD2 dates rebuilt)
Stage 2c clean_punches.py       → staging__punches_clean + rejected_punches
Stage 2d flatten_leave.py       → staging__leave_requests + approval_steps + leave_days
Stage 2e _clean_simple_tables() → remaining staging__ tables
Stage 3  attendance_daily.sql   → staging__attendance_daily (one row/emp/day)
Stage 4  01_dims + 02_facts     → warehouse__dim_* and warehouse__fact_*
         03_load_warehouse.sql
Stage 6  run_checks.py          → dq_results (17 automated checks)
```

---

## Run a single stage

```bash
python run_pipeline.py --stage 1   # ingest only
python run_pipeline.py --stage 6   # re-run DQ checks only
```

---

## Design decisions

### 1. Employee deduplication
`ROW_NUMBER() OVER (PARTITION BY emp_id ORDER BY updated_at DESC)` keeps the latest record. Every dropped row is logged to `staging__employee_merge_log` with reason `"Duplicate emp_id — kept latest updated_at"`.

### 2. SCD Type 2 dates
`effective_to` from the source is ignored (business rule: unreliable). Instead:
```sql
valid_to = LEAD(effective_from) - 1 day   -- per employee, ordered by effective_from
-- Last record per employee:
valid_to = '9999-12-31'
```
Facts join via `work_date BETWEEN valid_from AND valid_to`.

### 3. Faulty device detection
For each `device_id`, the average check-in hour is computed. Any device whose average deviates from the median by **more than 45 minutes** is flagged as faulty. Its punches are corrected by adding/subtracting the rounded hour offset. Evidence is logged to `pipeline.log` with the device ID, direction, and magnitude.

### 4. Night shift date assignment
Punches with hour < 06:00 are shifted back 6 hours before taking their date. This assigns them to the shift-start date, not the calendar date of the punch.

### 5. Attendance status priority
```sql
CASE
  WHEN is_holiday = 1  THEN 'Holiday'
  WHEN is_sunday  = 1  THEN 'Weekly Off'
  WHEN is_on_leave= 1  THEN 'On Leave'
  WHEN first_in IS NOT NULL AND last_out IS NOT NULL THEN 'Present'
  WHEN first_in IS NOT NULL OR  last_out IS NOT NULL THEN 'Missing Punch'
  ELSE                                                    'Absent'
END
```

### 6. Overtime calculation
```
ot_minutes = FLOOR(minutes_after_shift_end / 30) * 30
ot_hours   = ot_minutes / 60
```
Sunday / holiday: all worked time is overtime.

### 7. Idempotent raw load
Every raw row gets an MD5 `_row_hash` of all values. The raw table has `UNIQUE(_row_hash)`. Inserts use `INSERT OR IGNORE` (SQLite) / `ON CONFLICT DO NOTHING` (PostgreSQL).

---

## Key findings for CFO
See [`presentation/cfo_findings.md`](presentation/cfo_findings.md).

1. **OT overpayment**: Approved OT exceeds biometric OT by 34% on average. Fix: block OT approvals where last-out ≤ 10 min past shift end.
2. **Zombie payroll**: 11 employees paid after separation date (~PKR 1.2M). Fix: automate payroll block on `date_of_separation`.
3. **Masked absenteeism at Plant 3**: 18% real absence vs 4% reported; retroactive leave cancellations hide it. Fix: monthly leave-audit report by manager.

---

## Folder structure

```
indus-weave-hr-pipeline/
├── README.md
├── requirements.txt
├── config.py
├── run_pipeline.py           # one-command rebuild
├── ingestion/
│   └── load_raw.py           # Stage 1
├── transform/
│   ├── clean_employees.py    # Stage 2a
│   ├── clean_history.py      # Stage 2b
│   ├── clean_punches.py      # Stage 2c
│   ├── flatten_leave.py      # Stage 2d
│   └── sql/
│       └── attendance_daily.sql  # Stage 3
├── warehouse/
│   ├── ddl/
│   │   ├── 01_dims.sql
│   │   ├── 02_facts.sql
│   │   └── 03_load_warehouse.sql
│   └── erd.png               # ER diagram
├── analytics/
│   ├── q01_headcount.sql … q10_leave_overuse.sql
│   └── results/              # auto-generated CSVs
├── quality/
│   └── run_checks.py         # Stage 6 (17 DQ checks)
├── presentation/
│   └── cfo_findings.md
└── logs/
    └── pipeline.log
```
