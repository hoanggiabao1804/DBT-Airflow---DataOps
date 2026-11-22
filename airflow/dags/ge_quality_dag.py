"""ge_data_quality: stand-alone Great Expectations validation of the Silver layer.

``dbt_transform`` already runs GX right after ``dbt_test`` (gate before docs).
This DAG answers a different question: *is the data still valid now?* It
re-validates between pipeline runs (changes made outside dbt, manual fixes,
restored backups) and can be triggered on demand during an incident::

    wait_for_transform_idle -> check_runtime -> ge_validate -> publish_quality_report

* ``wait_for_transform_idle`` - sensor (reschedule mode): never validate while
  dbt_transform is rebuilding the same tables, which would give false failures.
* ``ge_validate`` - the same runner/evidence contract as dbt_transform (Tuan's
  ``run_airflow_quality_task.py ge``): customer + order checkpoints.
* ``publish_quality_report`` - runs even if GX failed (``all_done``); reads the
  runner's ``task_summary.json`` + ``ge/summary.json``, records a
  ``data_quality`` metric per checkpoint and sends one alert: critical when an
  expectation failed (exit 1) or GX could not run (exit 2).

Schedule: ``DATAOPS_GE_SCHEDULE`` (default every 6 hours at minute 30).
Param ``schema`` (default ``DATAOPS_GE_SCHEMA`` = silver) lets an operator
validate another schema with the same suites, e.g. a restored copy during an
incident or the ``dq_drill`` schema used to rehearse data-quality alerts.
"""

from datetime import timedelta
import json
import os

import pendulum
from airflow import DAG
from airflow.exceptions import AirflowFailException
from airflow.models.param import Param
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor

from utils.alerting import send_alert
from utils.callbacks import TASK_CALLBACKS, on_dag_failure, on_dag_success, on_task_failure_metric_only
from utils.logging_utils import record_metric
from utils.operators import QualityStepOperator
from utils.pipeline import CHECK_RUNTIME, DATA_FAILURE_EXIT_CODE, LOCAL_TIMEZONE, RUNNER, dbt_target, ge_schema
from utils.pipeline import latest_task_summary
from utils.pipeline import resolve_schedule, runner_env

TRANSFORM_DAG_ID = "dbt_transform"


def transform_idle():
    from airflow.models import DagRun  # pylint: disable=import-outside-toplevel
    from airflow.utils.state import DagRunState  # pylint: disable=import-outside-toplevel

    active = DagRun.find(dag_id=TRANSFORM_DAG_ID, state=DagRunState.RUNNING) + DagRun.find(
        dag_id=TRANSFORM_DAG_ID, state=DagRunState.QUEUED
    )
    if active:
        print("Waiting: {} active run(s) of {}".format(len(active), TRANSFORM_DAG_ID))
    return not active


def publish_quality_report(**context):
    ti = context["ti"]
    summary, folder = latest_task_summary(ti.dag_id, context["run_id"], "ge_validate")
    ge_state = context["dag_run"].get_task_instance("ge_validate").state
    if summary is None and ge_state in ("upstream_failed", "skipped"):
        # check_runtime/sensor already failed and alerted; do not page twice.
        raise AirflowFailException("ge_validate did not run (state {})".format(ge_state))
    if summary is None:
        send_alert(
            "Data quality: no GX result",
            "ge_validate produced no task_summary.json (did it start?).",
            severity="critical",
            context=context,
        )
        raise AirflowFailException("No ge_validate evidence found")

    validations = []
    ge_file = folder / "ge" / "summary.json"
    if ge_file.is_file():
        validations = json.loads(ge_file.read_text(encoding="utf-8")).get("validations", [])
    for validation in validations:
        stats = validation.get("statistics", {})
        record_metric(
            "data_quality",
            context,
            checkpoint=validation.get("checkpoint"),
            suite=validation.get("suite"),
            success=validation.get("success"),
            evaluated=stats.get("evaluated_expectations"),
            failed=stats.get("unsuccessful_expectations"),
            success_percent=stats.get("success_percent"),
        )
    lines = [
        "{}: {}/{} expectations passed".format(
            v.get("checkpoint"),
            v.get("statistics", {}).get("successful_expectations"),
            v.get("statistics", {}).get("evaluated_expectations"),
        )
        for v in validations
    ]
    status, exit_code = summary.get("status"), summary.get("exit_code")
    print("GX status={} exit={} schema={}".format(status, exit_code, summary.get("schema")))
    print("\n".join(lines) or "no validation details")
    print("Evidence:", folder)
    if status == "passed" and exit_code == 0:
        return "passed"
    cause = "expectations failed" if exit_code == 1 else "GX execution error"
    send_alert(
        "Data quality FAILED on {}".format(summary.get("schema")),
        "{} (exit {}). {}".format(cause, exit_code, " | ".join(lines)),
        severity="critical",
        context=context,
        ge_status=status,
        evidence=str(folder),
    )
    raise AirflowFailException("Data quality failed: " + cause)


with DAG(
    "ge_data_quality",
    default_args={
        "owner": "dataops",
        "retries": 1,
        "retry_delay": timedelta(minutes=2),
        "execution_timeout": timedelta(minutes=20),
        **TASK_CALLBACKS,
    },
    description="Great Expectations re-validation of Silver with data-quality alerts",
    schedule=resolve_schedule(os.environ.get("DATAOPS_GE_SCHEDULE"), "30 */6 * * *"),
    start_date=pendulum.datetime(2026, 11, 1, tz=pendulum.timezone(LOCAL_TIMEZONE)),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    is_paused_upon_creation=True,
    on_success_callback=on_dag_success,
    on_failure_callback=on_dag_failure,
    params={
        "schema": Param(
            ge_schema(), type="string", pattern=r"^[A-Za-z_][A-Za-z0-9_]*$", description="Schema to validate"
        )
    },
    tags=["great-expectations", "data-quality", "dataops"],
    doc_md=__doc__,
) as dag:
    wait = PythonSensor(
        task_id="wait_for_transform_idle",
        python_callable=transform_idle,
        mode="reschedule",
        poke_interval=60,
        timeout=60 * 60,
        retries=0,
    )
    check_runtime = BashOperator(
        task_id="check_runtime",
        bash_command=CHECK_RUNTIME,
        env={"DATAOPS_DBT_TARGET": dbt_target()},
        append_env=True,
        retries=2,
        retry_delay=timedelta(seconds=30),
        execution_timeout=timedelta(minutes=3),
        do_xcom_push=False,
    )
    ge_validate = QualityStepOperator(
        task_id="ge_validate",
        bash_command=RUNNER + "ge",
        env=dict(runner_env(), DATAOPS_GE_SCHEMA="{{ params.schema }}"),
        append_env=True,
        # Retry once for infrastructure hiccups (exit 2); expectations failed (exit 1) fails at once.
        retries=1,
        no_retry_exit_codes=(DATA_FAILURE_EXIT_CODE,),
        # publish_quality_report sends the detailed alert; record the metric only.
        on_failure_callback=on_task_failure_metric_only,
        skip_on_exit_code=None,
        do_xcom_push=False,
    )
    report = PythonOperator(
        task_id="publish_quality_report",
        python_callable=publish_quality_report,
        trigger_rule="all_done",
        retries=0,
        # Alerting is done inside the task with GX details; avoid a second generic page.
        on_failure_callback=None,
    )
    wait >> check_runtime >> ge_validate >> report
