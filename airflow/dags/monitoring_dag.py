"""dataops_monitoring: periodic health check of the DataOps stack.

Every 30 minutes (``DATAOPS_MONITORING_SCHEDULE``) four independent checks run,
then ``publish_report`` combines them::

    check_services ─┐
    check_pipeline ─┤
    check_metrics  ─┼─> publish_report  (trigger_rule=all_done)
    check_disk     ─┘

* services  - all 6 Compose services running and not unhealthy
* pipeline  - last ``dbt_transform`` run did not fail; last success is recent
* metrics   - ``dbt_transform`` task success rate over the last 24 h
* disk      - free space where logs and quality evidence are written

``publish_report`` writes ``logs/dataops_monitoring/latest.json`` and
``history.jsonl`` and alerts **only when the overall status changes** (or a
problem persists for 6 h), so an incident pages once, and recovery is announced.
Check tasks never fail on a bad result - they return it; a task failure here
means the monitor itself is broken (and that is alerted by the callback).
"""

from datetime import datetime, timedelta, timezone
import os

import pendulum
from airflow import DAG
from airflow.operators.python import PythonOperator

from utils import monitoring
from utils.callbacks import on_task_failure
from utils.logging_utils import read_metrics
from utils.pipeline import LOCAL_TIMEZONE, resolve_schedule

PIPELINE_DAG_ID = "dbt_transform"
CHECKS = ("check_services", "check_pipeline", "check_metrics", "check_disk")


def _guard(name, function):
    """Run a check; an unexpected exception becomes a critical result, not a task failure."""
    try:
        return function()
    except Exception as error:  # noqa: BLE001
        return monitoring.result(name, monitoring.CRITICAL, "check error: {}".format(type(error).__name__))


def services_check():
    project = os.environ.get("DATAOPS_COMPOSE_PROJECT", "")
    return _guard("services", lambda: monitoring.check_services(monitoring.docker_containers(project)))


def pipeline_check():
    def run():
        from airflow.models import DagModel, DagRun  # pylint: disable=import-outside-toplevel
        from airflow.utils.session import create_session  # pylint: disable=import-outside-toplevel

        with create_session() as session:
            rows = (
                session.query(DagRun)
                .filter(DagRun.dag_id == PIPELINE_DAG_ID)
                .order_by(DagRun.execution_date.desc())
                .limit(20)
                .all()
            )
            runs = [{"run_id": r.run_id, "state": r.state, "end_date": r.end_date} for r in rows]
            dag = session.query(DagModel).filter(DagModel.dag_id == PIPELINE_DAG_ID).one_or_none()
            paused = bool(dag is None or dag.is_paused)
        scheduled = not paused and resolve_schedule(os.environ.get("DATAOPS_SCHEDULE"), "0 6 * * *") is not None
        check = monitoring.check_pipeline(
            runs,
            max_age_hours=monitoring.env_float("DATAOPS_PIPELINE_MAX_AGE_HOURS", 26),
            scheduled=scheduled,
        )
        check.update(paused=paused, scheduled=scheduled)
        return check

    return _guard("pipeline", run)


def metrics_check():
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    return _guard(
        "metrics",
        lambda: monitoring.check_metrics(
            read_metrics(since=since),
            min_success_rate=monitoring.env_float("DATAOPS_MIN_TASK_SUCCESS_RATE", 0.8),
            dag_id=PIPELINE_DAG_ID,
        ),
    )


def disk_check():
    return _guard(
        "disk",
        lambda: monitoring.check_disk(
            ["/opt/airflow/logs", "/opt/airflow/quality_evidence"],
            min_free_gb=monitoring.env_float("DATAOPS_DISK_MIN_FREE_GB", 2),
            warn_free_gb=monitoring.env_float("DATAOPS_DISK_WARN_FREE_GB", 5),
        ),
    )


def publish_report(**context):
    checks = []
    for task_id in CHECKS:
        value = context["ti"].xcom_pull(task_ids=task_id)
        if not isinstance(value, dict):
            value = monitoring.result(task_id.replace("check_", ""), monitoring.CRITICAL, "check produced no result")
        checks.append(value)
    report = monitoring.publish(monitoring.build_report(checks), context=context)
    for check in report["checks"]:
        print("{:<9} {:<8} {}".format(check["check"], check["status"].upper(), check["detail"]))
    print("OVERALL  ", report["status"].upper(), "| alert:", report.get("alert", {}).get("title", "none"))
    return report["status"]


with DAG(
    "dataops_monitoring",
    default_args={
        "owner": "dataops",
        "retries": 0,  # the next run in 30 minutes is the retry
        "execution_timeout": timedelta(minutes=5),
        "on_failure_callback": on_task_failure,
    },
    description="Health of services, pipeline freshness, task success rate and disk; alerts on change",
    schedule=resolve_schedule(os.environ.get("DATAOPS_MONITORING_SCHEDULE"), "*/30 * * * *"),
    start_date=pendulum.datetime(2026, 11, 1, tz=pendulum.timezone(LOCAL_TIMEZONE)),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=15),
    is_paused_upon_creation=False,  # a monitor that starts paused monitors nothing
    tags=["monitoring", "dataops"],
    doc_md=__doc__,
) as dag:
    report_task = PythonOperator(task_id="publish_report", python_callable=publish_report, trigger_rule="all_done")
    for task_id, callable_ in zip(CHECKS, (services_check, pipeline_check, metrics_check, disk_check)):
        PythonOperator(task_id=task_id, python_callable=callable_) >> report_task
