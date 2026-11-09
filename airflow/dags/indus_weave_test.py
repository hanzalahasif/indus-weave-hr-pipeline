from datetime import datetime
from airflow.sdk import DAG, task

with DAG(
    dag_id="indus_weave_test",
    start_date=datetime(2026, 11, 8),
    schedule=None,
    catchup=False,
    tags=["indus-weave", "learning"],
) as dag:

    @task
    def say_hello():
        print("Hello from Indus Weave HR Pipeline!")

    say_hello()
