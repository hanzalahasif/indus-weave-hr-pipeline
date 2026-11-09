from datetime import datetime

from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator

with DAG(
    dag_id="indus_weave_hr_pipeline",
    start_date=datetime(2026, 11, 8),
    schedule=None,
    catchup=False,
    tags=["indus-weave", "hr", "etl"],
) as dag:

    run_hr_pipeline = BashOperator(
        task_id="run_full_hr_pipeline",
        bash_command=(
            "/opt/airflow/venvs/indus/bin/python "
            "/opt/airflow/indus-weave-hr-pipeline/run_pipeline.py "
            "--reset --export"
        ),
    )
