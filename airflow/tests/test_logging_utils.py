"""Unit tests for airflow/dags/utils/logging_utils.py and callbacks.py.

Airflow is not required: contexts are simulated with SimpleNamespace objects
that expose the same attributes as TaskInstance/DagRun/DAG.

    python -m pytest airflow/tests -q
"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))

from utils import callbacks, logging_utils  # noqa: E402


@pytest.fixture(autouse=True)
def metrics_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATAOPS_METRICS_DIR", str(tmp_path / "metrics"))
    monkeypatch.setenv("DATAOPS_ALERT_DIR", str(tmp_path / "alerts"))
    monkeypatch.delenv("DATAOPS_ALERT_WEBHOOK_URL", raising=False)
    return tmp_path / "metrics"


def make_context(state="failed", try_number=2, exception=None, duration=12.5):
    start = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
    ti = SimpleNamespace(
        dag_id="dbt_transform",
        task_id="dbt_test",
        _try_number=try_number,
        try_number=try_number + 1,  # Airflow reports the *next* try after the attempt ends
        max_tries=2,
        state=state,
        start_date=start,
        end_date=start + timedelta(seconds=duration),
        duration=duration,
        log_url="http://localhost:8080/log?x=1",
        hostname="scheduler",
    )
    return {
        "dag": SimpleNamespace(dag_id="dbt_transform"),
        "dag_run": SimpleNamespace(run_id="manual-1", run_type="manual", state="running"),
        "task_instance": ti,
        "exception": exception,
    }


def test_context_fields_uses_attempt_that_just_ran():
    fields = logging_utils.context_fields(make_context(try_number=2))
    assert fields["try_number"] == 2
    assert fields["dag_id"] == "dbt_transform"
    assert fields["task_id"] == "dbt_test"
    assert fields["run_id"] == "manual-1"
    assert fields["duration_seconds"] == 12.5


def test_context_fields_tolerates_missing_parts():
    assert logging_utils.context_fields(None) == {}
    fields = logging_utils.context_fields({"dag": SimpleNamespace(dag_id="d"), "reason": "timed_out"})
    assert fields == {"dag_id": "d", "reason": "timed_out"}


def test_dag_level_ignores_last_task_instance():
    context = make_context(state="success")
    start = datetime(2026, 11, 19, 8, 0, tzinfo=timezone.utc)
    context["dag_run"] = SimpleNamespace(
        run_id="manual-1", run_type="manual", state="success", start_date=start, end_date=start + timedelta(seconds=42)
    )
    fields = logging_utils.context_fields(context, dag_level=True)
    assert "task_id" not in fields and "try_number" not in fields
    assert fields["duration_seconds"] == 42.0


def test_exception_message_is_bounded():
    fields = logging_utils.context_fields(make_context(exception=RuntimeError("x" * 2000)))
    assert fields["exception_type"] == "RuntimeError"
    assert len(fields["exception_message"]) == 500


def test_log_event_writes_prefixed_json(caplog):
    caplog.set_level("INFO", logger="dataops")
    logging_utils.log_event("task_start", make_context(state="running"))
    line = [r.getMessage() for r in caplog.records if r.getMessage().startswith(logging_utils.EVENT_PREFIX)][0]
    payload = json.loads(line[len(logging_utils.EVENT_PREFIX) :])
    assert payload["event"] == "task_start"
    assert payload["task_id"] == "dbt_test"


def test_callbacks_append_metrics(metrics_dir):
    callbacks.on_task_success(make_context(state="success", try_number=1, duration=3.0))
    callbacks.on_task_retry(make_context(state="up_for_retry", try_number=1))
    callbacks.on_task_failure(make_context(state="failed", try_number=2))
    callbacks.on_dag_failure({"dag": SimpleNamespace(dag_id="dbt_transform"), "reason": "task_failure"})
    records = list(logging_utils.read_metrics())
    assert [r["event"] for r in records] == ["task_success", "task_retry", "task_failure", "dag_failure"]
    summary = logging_utils.summarize_metrics(records)
    assert summary["task_success"] == 1 and summary["task_failure"] == 1 and summary["task_retry"] == 1
    assert summary["task_success_rate"] == 0.5
    assert summary["duration_seconds"]["dbt_test"]["avg"] == 3.0


def test_read_metrics_since_filters_and_skips_garbage(metrics_dir):
    path = metrics_dir / logging_utils.METRICS_FILENAME
    metrics_dir.mkdir(parents=True)
    path.write_text(
        '{"event": "task_success", "timestamp_utc": "2026-01-01T00:00:00+00:00"}\n'
        "not json\n"
        '{"event": "task_failure", "timestamp_utc": "2026-11-19T00:00:00+00:00"}\n',
        encoding="utf-8",
    )
    since = datetime(2026, 6, 1, tzinfo=timezone.utc)
    assert [r["event"] for r in logging_utils.read_metrics(since=since)] == ["task_failure"]


def test_callback_never_raises_even_if_metrics_dir_unwritable(monkeypatch, tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setenv("DATAOPS_METRICS_DIR", str(blocker / "sub"))  # parent is a file -> mkdir fails
    callbacks.on_task_failure(make_context())  # must not raise


def test_safe_wrapper_swallows_exceptions():
    @callbacks._safe  # pylint: disable=protected-access
    def broken(context):
        raise ValueError("boom")

    broken({})  # must not raise
