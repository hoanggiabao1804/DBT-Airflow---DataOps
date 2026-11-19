"""dataops_timeout_drill: rehearse a hung task being killed by execution_timeout.

Manual only (no schedule), paused at creation; it does not modify any table.
``dbt_test_with_timeout`` runs the real ``dbt test`` step (normally ~9 s) with a
5-second ``execution_timeout``. Expected outcome, verified in
docs/thinh_week3_day13.md:

1. Airflow raises AirflowTaskTimeout and calls ``on_kill`` -> SIGTERM.
2. The runner terminates the dbt process *inside* the dbt container
   (``task_summary.json``: status ``killed``, ``killed_container_processes`` > 0).
3. No retry (retries=0), a critical "Task failed" alert is sent.
4. ``scripts/health_check.py`` reports no orphan dbt process afterwards.
"""

from datetime import timedelta

import pendulum
from airflow import DAG

from utils.callbacks import TASK_CALLBACKS
from utils.operators import QualityStepOperator
from utils.pipeline import LOCAL_TIMEZONE, RUNNER, runner_env

with DAG(
    "dataops_timeout_drill",
    default_args={"owner": "dataops", "retries": 0, **TASK_CALLBACKS},
    description="Drill: dbt test killed by a 5 s execution_timeout must leave no orphan process",
    schedule=None,
    start_date=pendulum.datetime(2026, 11, 1, tz=pendulum.timezone(LOCAL_TIMEZONE)),
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=True,
    tags=["drill", "dataops"],
    doc_md=__doc__,
) as dag:
    QualityStepOperator(
        task_id="dbt_test_with_timeout",
        bash_command=RUNNER + "test",
        env=runner_env(),
        append_env=True,
        execution_timeout=timedelta(seconds=5),
        do_xcom_push=False,
    )
