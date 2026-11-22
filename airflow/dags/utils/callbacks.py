"""Airflow callbacks: DataOps metrics for every state change, alerts for problems.

Wire them through ``default_args`` (task level) and the ``DAG(...)`` call
(DAG level); see ``dbt_dag.py``. Every callback is wrapped by ``_safe`` so an
exception inside observability code is logged but never changes task state.

======================  ==========================================  =======  ==========
event                   when                                        metrics  alert
======================  ==========================================  =======  ==========
``task_start``          a task attempt begins                       log only -
``task_success``        a task attempt succeeds                     yes      -
``task_retry``          an attempt fails, Airflow will retry        yes      warning [1]
``task_failure``        last attempt fails (retries exhausted)      yes      critical
``dag_success``         the DAG run finishes successfully           yes      -
``dag_failure``         the DAG run fails                           yes      critical [2]
SLA miss                a task finishes later than its ``sla``      -        warning
======================  ==========================================  =======  ==========

[1] Disable with ``DATAOPS_ALERT_ON_RETRY=false`` if retries are too noisy.
[2] Only when the cause is *not* a task failure (e.g. ``dagrun_timeout``):
    the failing task already raised a critical alert, one incident = one page.
"""

import functools
import os

from utils.alerting import send_alert
from utils.logging_utils import get_logger, log_event, record_metric


def _safe(callback):
    @functools.wraps(callback)
    def wrapper(context):
        try:
            callback(context)
        except Exception:  # noqa: BLE001 - observability must never fail the task
            get_logger().exception("DataOps callback %s failed", callback.__name__)

    return wrapper


def _alert_on_retry():
    return os.environ.get("DATAOPS_ALERT_ON_RETRY", "true").strip().lower() not in ("0", "false", "no", "off")


@_safe
def on_task_execute(context):
    log_event("task_start", context)


@_safe
def on_task_success(context):
    record_metric("task_success", context)


@_safe
def on_task_retry(context):
    record = record_metric("task_retry", context)
    if _alert_on_retry():
        send_alert(
            "Task retry: {}.{}".format(record.get("dag_id"), record.get("task_id")),
            "Attempt {} of {} failed; Airflow will retry automatically.".format(
                record.get("try_number"), (record.get("max_tries") or 0) + 1
            ),
            severity="warning",
            context=context,
        )


@_safe
def on_task_failure(context):
    record = record_metric("task_failure", context)
    send_alert(
        "Task failed: {}.{}".format(record.get("dag_id"), record.get("task_id")),
        "All {} attempt(s) failed. Downstream tasks will not run.".format(record.get("try_number") or "?"),
        severity="critical",
        context=context,
    )


@_safe
def on_task_failure_metric_only(context):
    """For tasks whose failure is reported by a dedicated downstream alert."""
    record_metric("task_failure", context)


@_safe
def on_dag_success(context):
    record_metric("dag_success", context, dag_level=True)


@_safe
def on_dag_failure(context):
    record = record_metric("dag_failure", context, dag_level=True)
    reason = str(context.get("reason") or "")
    if reason and reason != "task_failure":
        send_alert(
            "DAG run failed: {}".format(record.get("dag_id")),
            "Run {} failed: {}.".format(record.get("run_id"), reason),
            severity="critical",
            context=context,
            dag_level=True,
        )


def on_sla_miss(dag, task_list, blocking_task_list, slas, blocking_tis):  # pylint: disable=unused-argument
    """``sla_miss_callback`` - note the different signature from task callbacks."""
    try:
        tasks = sorted({getattr(sla, "task_id", str(sla)) for sla in slas or []})
        send_alert(
            "SLA missed: {}".format(getattr(dag, "dag_id", dag)),
            "Tasks finished after their SLA: {}.".format(", ".join(tasks) or "-"),
            severity="warning",
            dag_id=getattr(dag, "dag_id", None),
        )
    except Exception:  # noqa: BLE001
        get_logger().exception("DataOps SLA callback failed")


TASK_CALLBACKS = {
    "on_execute_callback": on_task_execute,
    "on_success_callback": on_task_success,
    "on_retry_callback": on_task_retry,
    "on_failure_callback": on_task_failure,
}
