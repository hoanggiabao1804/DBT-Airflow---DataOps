"""Structured logging and lightweight metrics for DataOps DAGs.

Everything here uses only the Python standard library so the module can be
imported by the Airflow scheduler, by tests on a laptop, and by host scripts.

Two outputs are produced:

* A JSON line in the normal task log (``DATAOPS_EVENT {...}``) so that a person
  reading the Airflow UI log, or ``grep``-ing the log directory, sees the same
  fields for every event.
* An append-only metrics file (JSON Lines) under ``DATAOPS_METRICS_DIR``. The
  monitoring DAG and ``scripts/health_check.py`` read this file to compute
  success rate, retry count and duration without querying the Airflow database.

Nothing in this module may raise into a callback: observability must never turn
a successful task into a failed one, or hide the original failure.
"""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import socket

EVENT_PREFIX = "DATAOPS_EVENT "
DEFAULT_METRICS_DIR = "/opt/airflow/logs/dataops_metrics"
METRICS_FILENAME = "task_metrics.jsonl"
LOGGER_NAME = "dataops"


def utc_now():
    return datetime.now(timezone.utc)


def get_logger(name=LOGGER_NAME):
    """Return a logger that propagates to Airflow's task log handler."""
    logger = logging.getLogger(name)
    if not logger.handlers and not logging.getLogger().handlers:
        # Outside Airflow (tests, host scripts) there is no root handler yet.
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return logger


def metrics_dir():
    return Path(os.environ.get("DATAOPS_METRICS_DIR", DEFAULT_METRICS_DIR))


def _iso(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


def context_fields(context, dag_level=False):
    """Extract the identifying fields of an Airflow callback/task context.

    Accepts a full Airflow context dict or ``None``. Missing keys are tolerated.
    With ``dag_level=True`` task-instance fields are ignored: Airflow passes the
    *last* task instance to DAG callbacks, which would mislabel a DAG event.
    """
    context = context or {}
    fields = {}
    dag = context.get("dag")
    dag_run = context.get("dag_run")
    ti = None if dag_level else context.get("task_instance") or context.get("ti")
    if dag is not None:
        fields["dag_id"] = getattr(dag, "dag_id", None)
    if dag_run is not None:
        fields["run_id"] = getattr(dag_run, "run_id", None)
        fields["run_type"] = str(getattr(dag_run, "run_type", "") or "") or None
        fields["dag_run_state"] = str(getattr(dag_run, "state", "") or "") or None
        if dag_level:
            start, end = getattr(dag_run, "start_date", None), getattr(dag_run, "end_date", None)
            fields["start_date"] = _iso(start)
            fields["end_date"] = _iso(end)
            fields["duration_seconds"] = _duration(None, start, end)
    elif context.get("run_id"):
        fields["run_id"] = context["run_id"]
    if ti is not None:
        fields["dag_id"] = fields.get("dag_id") or getattr(ti, "dag_id", None)
        fields["task_id"] = getattr(ti, "task_id", None)
        fields["try_number"] = _attempt(ti)
        fields["max_tries"] = getattr(ti, "max_tries", None)
        fields["state"] = str(getattr(ti, "state", "") or "") or None
        start, end = getattr(ti, "start_date", None), getattr(ti, "end_date", None)
        fields["start_date"] = _iso(start)
        fields["end_date"] = _iso(end)
        fields["duration_seconds"] = _duration(ti, start, end)
        fields["log_url"] = getattr(ti, "log_url", None)
        fields["hostname"] = getattr(ti, "hostname", None)
    exception = context.get("exception")
    if exception is not None:
        # Only the class and a bounded message; never dump full tracebacks or rows.
        fields["exception_type"] = type(exception).__name__
        fields["exception_message"] = str(exception)[:500]
    reason = context.get("reason")
    if reason:
        fields["reason"] = str(reason)[:200]
    return {key: value for key, value in fields.items() if value is not None}


def _attempt(ti):
    """Return the 1-based attempt that just finished.

    In Airflow 2.7, ``try_number`` already points to the *next* try once a task
    instance has left the running state, so the attempt that produced the
    callback is ``try_number - 1``. ``_try_number`` is the raw stored value.
    """
    raw = getattr(ti, "_try_number", None)
    if isinstance(raw, int) and raw > 0:
        return raw
    value = getattr(ti, "try_number", None)
    return value if isinstance(value, int) else None


def _duration(ti, start, end):
    value = getattr(ti, "duration", None)
    if isinstance(value, (int, float)):
        return round(float(value), 3)
    if isinstance(start, datetime):
        end = end if isinstance(end, datetime) else utc_now()
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        return round((end - start).total_seconds(), 3)
    return None


def build_event(event, context=None, dag_level=False, **extra):
    record = {"event": event, "timestamp_utc": utc_now().isoformat(), "host": socket.gethostname()}
    record.update(context_fields(context, dag_level=dag_level))
    record.update({key: value for key, value in extra.items() if value is not None})
    return record


def log_event(event, context=None, level=logging.INFO, logger=None, dag_level=False, **extra):
    """Write one structured event line to the task log and return the record."""
    record = build_event(event, context, dag_level=dag_level, **extra)
    try:
        (logger or get_logger()).log(level, EVENT_PREFIX + json.dumps(record, sort_keys=True, default=str))
    except Exception:  # noqa: BLE001 - logging must not break the caller
        pass
    return record


def append_jsonl(path, record):
    """Append one JSON line; return True on success, False (never raise) on error."""
    try:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, sort_keys=True, default=str) + "\n"
        # A single os.write of a short line is atomic for O_APPEND files on Linux,
        # so concurrent tasks cannot interleave partial records.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664)
        try:
            os.write(fd, line.encode("utf-8"))
        finally:
            os.close(fd)
        return True
    except Exception:  # noqa: BLE001
        get_logger().warning("Could not append DataOps record to %s", path, exc_info=True)
        return False


def record_metric(event, context=None, dag_level=False, **extra):
    """Log an event and persist it to the metrics file."""
    record = log_event(event, context, dag_level=dag_level, **extra)
    append_jsonl(metrics_dir() / METRICS_FILENAME, record)
    return record


def read_metrics(path=None, since=None):
    """Yield metric records (optionally only those newer than ``since``)."""
    path = Path(path) if path else metrics_dir() / METRICS_FILENAME
    if not path.is_file():
        return
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if since is not None:
                try:
                    stamp = datetime.fromisoformat(record["timestamp_utc"])
                except (KeyError, ValueError):
                    continue
                if stamp < since:
                    continue
            yield record


def summarize_metrics(records):
    """Aggregate task-level metric records into counts and duration stats."""
    summary = {"task_success": 0, "task_failure": 0, "task_retry": 0, "dag_success": 0, "dag_failure": 0}
    durations = {}
    for record in records:
        event = record.get("event")
        if event in summary:
            summary[event] += 1
        if event == "task_success" and isinstance(record.get("duration_seconds"), (int, float)):
            durations.setdefault(record.get("task_id"), []).append(record["duration_seconds"])
    finished = summary["task_success"] + summary["task_failure"]
    summary["task_success_rate"] = round(summary["task_success"] / finished, 4) if finished else None
    summary["duration_seconds"] = {
        task: {"count": len(values), "avg": round(sum(values) / len(values), 3), "max": max(values)}
        for task, values in sorted(durations.items(), key=lambda item: str(item[0]))
    }
    return summary
