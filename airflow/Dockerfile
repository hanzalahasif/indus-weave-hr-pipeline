FROM apache/airflow:3.3.2

USER root

RUN apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
       curl ca-certificates unixodbc-dev libgssapi-krb5-2 msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/airflow/venvs/indus \
    && chown -R airflow:root /opt/airflow/venvs

COPY indus-requirements.txt /tmp/indus-requirements.txt

USER airflow

RUN python -m venv /opt/airflow/venvs/indus \
    && /opt/airflow/venvs/indus/bin/pip install --no-cache-dir -r /tmp/indus-requirements.txt
