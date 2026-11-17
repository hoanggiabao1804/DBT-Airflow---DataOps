# dbt and GX execute in separate containers; only the Docker client is needed.
FROM docker:27.5.1-cli AS docker-cli

FROM apache/airflow:2.7.1-python3.9

USER root
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker

USER airflow
COPY requirements.txt /opt/airflow/requirements.txt
# The official image supplies these packages. Keep its dependency graph intact.
RUN python -c "import airflow, psycopg2; assert airflow.__version__ == '2.7.1'" \
    && docker --version

COPY --chown=airflow:root dags/ /opt/airflow/dags/
# DAGs, scripts, dbt project and evidence are mounted by Compose at runtime.
