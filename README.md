# Indus Weave HR Pipeline

Python, pandas, and SQL Server pipeline for HR CSV/JSON data.

## What you need

- Python 3.11+
- SQL Server Express at `DESKTOP-LNP0AFF\SQLEXPRESS`
- Microsoft ODBC Driver 18 for SQL Server
- Windows Authentication

The project uses pandas to read the files, `pyodbc` to connect to SQL Server, and SQLAlchemy to send SQL and load tables. No database password is stored in the project.

## First-time setup

1. In SSMS, connect to `DESKTOP-LNP0AFF\SQLEXPRESS` using Windows Authentication.
2. Open `setup_sql_server.sql` in SSMS and execute it. This creates the `indus_weave` database if it does not exist.
3. Open PowerShell in the project folder and run:

```powershell
python -m pip install -r requirements.txt
python run_pipeline.py --reset --export
```

Stage 1 reads all CSV and JSON files from `data/raw/` and loads them into SQL Server. You do not need to use the SSMS Import Wizard. The remaining stages clean and transform the data, build the warehouse, run quality checks, and export Q01–Q10 results as CSVs under `analytics/results/`.

The server, database, and ODBC driver defaults are in `config.py`. Override them with `SQL_SERVER`, `SQL_DATABASE`, and `ODBC_DRIVER` environment variables if they change. Connection and SQL errors are shown by the pipeline.

To confirm the data is in SQL Server, run this query in SSMS:

```sql
USE indus_weave;
SELECT TOP (10) * FROM dbo.raw__employees;
```

## Run commands

```powershell
python run_pipeline.py                 # run all stages
python run_pipeline.py --reset --export # drop pipeline tables, rebuild, export results
python run_pipeline.py --stage 1        # reload raw CSV/JSON tables only
python run_pipeline.py --stage 2        # clean and stage data
python run_pipeline.py --stage 3        # build daily attendance
python run_pipeline.py --stage 4        # build warehouse
python run_pipeline.py --stage 6        # run data-quality checks
```

`--reset` drops only this pipeline's tables, not the SQL Server database itself.

## Source files

All source data belongs in `data/raw/`.

| File | Format |
|---|---|
| employees.csv | CSV |
| employment_history.csv | CSV |
| departments.csv | CSV |
| shifts.json | JSON |
| shift_roster.csv | CSV |
| device_mapping.csv | CSV |
| biometric_punches.csv | CSV |
| holidays.csv | CSV |
| leave_requests.json | JSON |
| overtime_requests.csv | CSV |
| payroll_lines.csv | CSV |
| applications.csv | CSV |

## Pipeline stages

1. `ingestion/load_raw.py` loads source files into `dbo.raw__*`.
2. `transform/` cleans employee, employment-history, punch, leave, and other data into `dbo.staging__*`.
3. `transform/build_attendance.py` creates daily attendance.
4. `warehouse/ddl/` creates and loads warehouse dimensions and facts.
5. `quality/run_checks.py` writes data-quality results to `dbo.dq_results`.
6. Queries in `analytics/` export results to CSV.

Raw tables are replaced from source files on each ingestion run, so rerunning does not append duplicate imports.

## Business rules

- Employee duplicates keep the latest `updated_at` record.
- Employment-history `valid_to` is derived from the next `effective_from`; the last row is `9999-12-31`.
- Duplicate biometric punches within two minutes are rejected.
- Night-shift punches are assigned to the shift-start date.
- Overtime is rounded down to 30-minute blocks.

For a beginner-friendly explanation of the folders, files, dependencies, and
the end-to-end data flow, see [PROJECT_GUIDE.md](PROJECT_GUIDE.md).
