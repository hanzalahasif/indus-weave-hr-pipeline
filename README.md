# Indus Weave – HR Data Engineering Pipeline

A Python-based HR Data Engineering project that processes raw HR data, performs data cleaning and transformation, and loads structured data into Microsoft SQL Server for analytics and reporting.

The project demonstrates an end-to-end ETL workflow, with Apache Airflow and Docker included for workflow orchestration.

## Project Overview

HR data is often stored across multiple CSV files and requires cleaning, standardization, validation, and integration before it can be used for reporting.

This project builds an ETL pipeline to:

- Ingest raw HR datasets from CSV files.
- Clean and transform data using Python and Pandas.
- Handle missing values, inconsistent records, and data quality issues.
- Process HR-related information, including employee and attendance data.
- Load structured data into Microsoft SQL Server.
- Organize data for analytical queries and reporting.
- Export processed data for further use.

## Technologies Used

| Technology | Purpose |
|---|---|
| Python | ETL development and pipeline logic |
| Pandas | Data manipulation and transformation |
| NumPy | Numerical operations |
| SQL Server | Data storage and querying |
| SQLAlchemy | Database connectivity |
| PyODBC | SQL Server connectivity |
| Apache Airflow | Workflow orchestration |
| Docker | Containerized Airflow environment |
| Git & GitHub | Version control |

## ETL Workflow

```text
Raw HR CSV Files
       |
       v
Data Ingestion
       |
       v
Data Cleaning
       |
       v
Data Transformation
       |
       v
Data Quality Checks
       |
       v
SQL Server Database
       |
       v
Analytics & Data Export
```

## Project Structure

```text
indus-weave-hr-pipeline/
│
├── data/
│   └── raw/
│
├── sql/
│
├── airflow/
│   ├── dags/
│   ├── Dockerfile
│   ├── docker-compose.yaml
│   └── indus-requirements.txt
│
├── config.py
├── run_pipeline.py
├── requirements.txt
├── Dockerfile
├── .gitignore
└── README.md
```

## Getting Started

### 1. Clone the Repository

```bash
git clone https://github.com/hanzalahasif/indus-weave-hr-pipeline.git

cd indus-weave-hr-pipeline
```

### 2. Create a Virtual Environment

**Windows:**

```bash
python -m venv .venv
.venv\Scripts\activate
```

**Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure SQL Server

Configure your SQL Server connection through the environment variables used by `config.py`.

You will need:

- SQL Server instance name
- Database name
- ODBC Driver 18 for SQL Server
- Appropriate authentication credentials

Do not commit your actual database passwords or credentials to GitHub.

### 5. Run the Pipeline

Run the complete pipeline:

```bash
python run_pipeline.py
```

Run a specific stage:

```bash
python run_pipeline.py --stage 1
```

Reset existing pipeline tables before execution:

```bash
python run_pipeline.py --reset
```

Run the pipeline and export processed data:

```bash
python run_pipeline.py --export
```

**Important:** The `--reset` option can drop existing pipeline tables. Use it carefully.

## Apache Airflow Orchestration

The repository also includes an Apache Airflow setup using Docker Compose.

The Airflow DAG is designed to orchestrate the HR pipeline.

Airflow-related files are available in:

```text
airflow/
```

The Airflow environment requires its own configuration, dependencies, database connectivity, and appropriate ODBC driver setup.

## Key Learning Outcomes

Through this project, I worked with:

- Building ETL pipelines using Python.
- Data cleaning and transformation with Pandas.
- Connecting Python applications to SQL Server.
- Structuring data for analytical workloads.
- Handling database operations and pipeline execution.
- Workflow orchestration using Apache Airflow.
- Containerization concepts using Docker.
- Version control and project management with Git and GitHub.
## Author

**Hanzalah Asif**

GitHub: [@hanzalahasif](https://github.com/hanzalahasif)

Project Repository: [Indus Weave HR Data Engineering Pipeline](https://github.com/hanzalahasif/indus-weave-hr-pipeline)
