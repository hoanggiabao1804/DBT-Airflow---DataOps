"""Airflow callbacks that turn task/DAG state changes into DataOps metrics.

Wire them through ``default_args`` (task level) and the ``DAG(...)`` call
(DAG level); see ``dbt_dag.py``. Every callback is wrapped by ``_safe`` so an
exception inside observability code is logged but never changes task state.

Events written to the metrics file (``utils.logging_utils``):

======================  ==========================================  =========
event                   when                                        file
======================  ==========================================  =========
``task_start``          a task attempt begins (log only)            no
``task_success``        a task attempt succeeds                     yes
``task_retry``          an attempt fails, Airflow will retry        yes
``task_failure``        last attempt fails (retries exhausted)      yes
``dag_success``         the DAG run finishes successfully           yes
``dag_failure``         the DAG run fails (incl. dagrun_timeout)    yes
======================  ==========================================  =========
"""

import functools

from utils.logging_utils import get_logger, log_event, record_metric


def _safe(callback):
    @functools.wraps(callback)
    def wrapper(context):
        try:
            callback(context)
        except Exception:  # noqa: BLE001 - observability must never fail the task
            get_logger().exception("DataOps callback %s failed", callback.__name__)

    return wrapper


@_safe
def on_task_execute(context):
    log_event("task_start", context)


@_safe
def on_task_success(context):
    record_metric("task_success", context)


@_safe
def on_task_retry(context):
    record_metric("task_retry", context)


@_safe
def on_task_failure(context):
    record_metric("task_failure", context)


@_safe
def on_dag_success(context):
    record_metric("dag_success", context, dag_level=True)


@_safe
def on_dag_failure(context):
    record_metric("dag_failure", context, dag_level=True)


TASK_CALLBACKS = {
    "on_execute_callback": on_task_execute,
    "on_success_callback": on_task_success,
    "on_retry_callback": on_task_retry,
    "on_failure_callback": on_task_failure,
}
