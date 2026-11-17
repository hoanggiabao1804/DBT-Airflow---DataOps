"""Run dbt and both GX checkpoints before publishing dbt documentation."""

from datetime import datetime, timedelta
import os

from airflow import DAG
from airflow.operators.bash import BashOperator

with DAG(
    "dbt_transform",
    default_args={
        "owner": "tuan",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
        "execution_timeout": timedelta(minutes=20),
    },
    description="dbt models, data tests, GX customer/order checkpoints and dbt docs",
    # Manual by default for the historical lab dataset; Thinh can set a cron schedule.
    schedule=os.environ.get("DATAOPS_SCHEDULE") or None,
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,
    tags=["dbt", "sqlserver", "data-quality"],
    doc_md="""
    Builds Bronze/Silver/Gold, runs dbt tests, then both checked-in GX checkpoints.
    Any nonzero exit fails the task and blocks downstream documentation generation.
    Each attempt preserves its own artifacts under quality_evidence/airflow/.
    Historical source freshness is reported separately (DQ-W2-01); this DAG does
    not claim the source freshness SLA passed. See docs/tuan_week3_day11_12.md.
    """,
) as dag:
    steps = []
    for action, task_id in (
        ("deps", "dbt_deps"),
        ("run", "dbt_run"),
        ("test", "dbt_test"),
        ("ge", "ge_validate"),
        ("docs", "dbt_docs"),
    ):
        steps.append(
            BashOperator(
                task_id=task_id,
                bash_command="python /opt/airflow/scripts/run_airflow_quality_task.py " + action,
                env={
                    "DATAOPS_DAG_ID": "{{ dag.dag_id }}",
                    "DATAOPS_RUN_ID": "{{ run_id }}",
                    "DATAOPS_TASK_ID": "{{ task.task_id }}",
                    "DATAOPS_TRY_NUMBER": "{{ ti.try_number }}",
                    "DATAOPS_DBT_TARGET": os.environ.get("DATAOPS_DBT_TARGET", "dev"),
                    "DATAOPS_GE_SCHEMA": os.environ.get("DATAOPS_GE_SCHEMA", "silver"),
                },
                append_env=True,
                skip_on_exit_code=None,
                do_xcom_push=False,
            )
        )
    for upstream, downstream in zip(steps, steps[1:]):
        upstream >> downstream
