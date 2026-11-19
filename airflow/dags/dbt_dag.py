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
``$DATAOPS_METRICS_DIR/task_metrics.jsonl`` (see ``utils/callbacks.py``).
"""

from datetime import timedelta
import os

import pendulum
from airflow import DAG
from airflow.operators.bash import BashOperator

from utils.callbacks import TASK_CALLBACKS, on_dag_failure, on_dag_success

LOCAL_TZ = pendulum.timezone("Asia/Ho_Chi_Minh")
DEFAULT_SCHEDULE = "0 6 * * *"
RUNNER = "python /opt/airflow/scripts/run_airflow_quality_task.py "


def resolve_schedule(value):
    """Map DATAOPS_SCHEDULE to an Airflow schedule. Empty -> default cron."""
    value = (value or "").strip()
    if not value:
        return DEFAULT_SCHEDULE
    if value.lower() in ("manual", "none", "off"):
        return None
    return value


# Per-step policy. dbt_deps talks to the dbt package hub (network) so it gets
# more retries; transformations get longer timeouts. Timeouts are generous
# relative to the measured baseline (whole DAG ~5 minutes) so that a timeout
# really means "stuck", not "slow day".
STEPS = (
    # task_id,       runner action, retries, execution_timeout
    ("dbt_deps", "deps", 3, timedelta(minutes=10)),
    ("dbt_run", "run", 2, timedelta(minutes=30)),
    ("dbt_test", "test", 2, timedelta(minutes=20)),
    ("ge_validate", "ge", 1, timedelta(minutes=20)),
    ("dbt_docs", "docs", 1, timedelta(minutes=10)),
)

# Fail fast with a clear message when the stack is not up, instead of letting
# dbt_deps fail with a Docker error. dbt debug also proves SQL Server login.
CHECK_RUNTIME = r"""
set -euo pipefail
: "${DATAOPS_COMPOSE_PROJECT:?DATAOPS_COMPOSE_PROJECT is not set}"
for service in dbt ge-worker; do
  ids=$(docker ps -q --filter "label=com.docker.compose.project=${DATAOPS_COMPOSE_PROJECT}" \
        --filter "label=com.docker.compose.service=${service}" --filter status=running)
  count=$(printf '%s' "$ids" | grep -c . || true)
  if [ "$count" -ne 1 ]; then
    echo "Service ${service}: expected 1 running container, found ${count}"; exit 1
  fi
  echo "Service ${service}: running (${ids})"
done
dbt_id=$(docker ps -q --filter "label=com.docker.compose.project=${DATAOPS_COMPOSE_PROJECT}" \
         --filter "label=com.docker.compose.service=dbt" --filter status=running)
if docker exec -w /usr/app/dbt "$dbt_id" dbt debug --target "${DATAOPS_DBT_TARGET}" > /tmp/dbt_debug.log 2>&1; then
  echo "dbt debug: OK (target ${DATAOPS_DBT_TARGET})"
else
  echo "dbt debug: FAILED (target ${DATAOPS_DBT_TARGET}) - SQL Server down or profile invalid"
  grep -E "Connection test|ERROR|Error" /tmp/dbt_debug.log | head -5 || true
  exit 1
fi
"""

TARGET = os.environ.get("DATAOPS_DBT_TARGET", "dev")
GE_SCHEMA = os.environ.get("DATAOPS_GE_SCHEMA", "silver")
TASK_ENV = {
    "DATAOPS_DAG_ID": "{{ dag.dag_id }}",
    "DATAOPS_RUN_ID": "{{ run_id }}",
    "DATAOPS_TASK_ID": "{{ task.task_id }}",
    "DATAOPS_TRY_NUMBER": "{{ ti.try_number }}",
    "DATAOPS_DBT_TARGET": TARGET,
    "DATAOPS_GE_SCHEMA": GE_SCHEMA,
}

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
    schedule=resolve_schedule(os.environ.get("DATAOPS_SCHEDULE")),
    start_date=pendulum.datetime(2026, 11, 1, tz=LOCAL_TZ),
    catchup=False,  # historical dataset: never backfill missed days
    max_active_runs=1,  # two runs would write the same dbt tables
    dagrun_timeout=timedelta(hours=2),
    is_paused_upon_creation=True,
    on_success_callback=on_dag_success,
    on_failure_callback=on_dag_failure,
    tags=["dbt", "sqlserver", "data-quality", "dataops"],
    doc_md=__doc__,
) as dag:
    check_runtime = BashOperator(
        task_id="check_runtime",
        bash_command=CHECK_RUNTIME,
        env={"DATAOPS_DBT_TARGET": TARGET},
        append_env=True,
        retries=2,
        retry_delay=timedelta(seconds=30),
        execution_timeout=timedelta(minutes=3),
        do_xcom_push=False,
        doc_md="Verifies dbt/ge-worker containers are running and dbt can log in to SQL Server.",
    )

    previous = check_runtime
    for task_id, action, retries, timeout in STEPS:
        task = BashOperator(
            task_id=task_id,
            bash_command=RUNNER + action,
            env=TASK_ENV,
            append_env=True,
            retries=retries,
            execution_timeout=timeout,
            skip_on_exit_code=None,  # exit 1 (data) and 2 (execution) both fail the task
            do_xcom_push=False,
        )
        previous >> task
        previous = task
