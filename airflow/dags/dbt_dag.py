"""dbt_transform: Bronze -> Silver -> Gold, dbt tests, GX checkpoints, dbt docs.

Owner of the orchestration layer: Thinh (Airflow, Monitoring & Integration).
The quality steps themselves (dbt tests, GX checkpoints, evidence layout) are
owned by Tuan and executed through ``scripts/run_airflow_quality_task.py``.

Flow (every edge is ``all_success``; any failure stops everything downstream)::

    check_runtime -> dbt_deps -> dbt_run -> dbt_test -> ge_validate -> dbt_docs

Configuration (environment of BOTH webserver and scheduler):

* ``DATAOPS_SCHEDULE``  cron expression, preset (``@daily``) or ``manual``.
  Default ``0 6 * * *`` = 06:00 every day, Asia/Ho_Chi_Minh.
* ``DATAOPS_DBT_TARGET`` dbt target (default ``dev``).
* ``DATAOPS_GE_SCHEMA``  schema validated by GX (default ``silver``).

Observability: every task start/success/retry/failure and the DAG outcome are
written as ``DATAOPS_EVENT`` JSON lines in the task log and appended to
``$DATAOPS_METRICS_DIR/task_metrics.jsonl``. Retries raise a warning alert,
final failures a critical alert, and a scheduled run that has not finished
within 1 hour after its interval raises an SLA warning (``utils/callbacks.py``,
``utils/alerting.py``).
"""

from datetime import timedelta
import os

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

from utils.callbacks import TASK_CALLBACKS, on_dag_failure, on_dag_success, on_sla_miss
from utils.operators import QualityStepOperator
from utils.pipeline import CHECK_RUNTIME, DATA_FAILURE_EXIT_CODE, LOCAL_TIMEZONE, RUNNER, dbt_target
from utils.pipeline import resolve_schedule, runner_env

DEFAULT_SCHEDULE = "0 6 * * *"

# Per-step policy. dbt_deps talks to the dbt package hub (network) so it gets
# more retries; transformations get longer timeouts. Timeouts are generous
# relative to the measured baseline (whole DAG ~45 seconds) so that a timeout
# really means "stuck", not "slow day".
STEPS = (
    # task_id,       runner action, retries, execution_timeout
    ("dbt_deps", "deps", 3, timedelta(minutes=10)),
    ("dbt_run", "run", 2, timedelta(minutes=30)),
    ("dbt_test", "test", 2, timedelta(minutes=20)),
    ("ge_validate", "ge", 1, timedelta(minutes=20)),
    ("dbt_docs", "docs", 1, timedelta(minutes=10)),
)

with DAG(
    "dbt_transform",
    default_args={
        "owner": "dataops",
        "depends_on_past": False,
        "email_on_failure": False,
        "email_on_retry": False,
        "retries": 2,
        "retry_delay": timedelta(minutes=1),
        # 1 min, 2 min, 4 min ... capped: transient SQL Server/Docker hiccups
        # get time to recover without a long fixed wait.
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=10),
        "execution_timeout": timedelta(minutes=20),
        # Structured log line + metrics record for every start/success/retry/failure.
        **TASK_CALLBACKS,
    },
    description="dbt Bronze/Silver/Gold, dbt tests, GX checkpoints and dbt docs",
    schedule=resolve_schedule(os.environ.get("DATAOPS_SCHEDULE"), DEFAULT_SCHEDULE),
    start_date=pendulum.datetime(2026, 11, 1, tz=pendulum.timezone(LOCAL_TIMEZONE)),
    catchup=False,  # historical dataset: never backfill missed days
    max_active_runs=1,  # two runs would write the same dbt tables
    dagrun_timeout=timedelta(hours=2),
    is_paused_upon_creation=True,
    on_success_callback=on_dag_success,
    on_failure_callback=on_dag_failure,
    sla_miss_callback=on_sla_miss,
    tags=["dbt", "sqlserver", "data-quality", "dataops"],
    doc_md=__doc__,
) as dag:
    check_runtime = BashOperator(
        task_id="check_runtime",
        bash_command=CHECK_RUNTIME,
        env={"DATAOPS_DBT_TARGET": dbt_target()},
        append_env=True,
        retries=2,
        retry_delay=timedelta(seconds=30),
        execution_timeout=timedelta(minutes=3),
        do_xcom_push=False,
        doc_md="Verifies dbt/ge-worker containers are running and dbt can log in to SQL Server.",
    )

    previous = check_runtime
    for task_id, action, retries, timeout in STEPS:
        task = QualityStepOperator(
            task_id=task_id,
            bash_command=RUNNER + action,
            env=runner_env(),
            append_env=True,
            retries=retries,
            execution_timeout=timeout,
            skip_on_exit_code=None,  # exit 1 (data) and 2 (execution) both fail the task
            # GX exit 1 = expectations failed: fail at once. dbt also returns 1 for
            # database errors, so dbt steps keep their retries for every exit code.
            no_retry_exit_codes=(DATA_FAILURE_EXIT_CODE,) if action == "ge" else (),
            do_xcom_push=False,
            # Scheduled runs: docs (the last step) must be done 1 h after the interval ends.
            sla=timedelta(hours=1) if task_id == "dbt_docs" else None,
        )
        previous >> task
        previous = task
