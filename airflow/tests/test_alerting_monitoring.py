"""Unit tests for utils/alerting.py, utils/monitoring.py and utils/pipeline.py."""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))

from utils import alerting, callbacks, monitoring, pipeline  # noqa: E402

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    for name in ("DATAOPS_METRICS_DIR", "DATAOPS_ALERT_DIR", "DATAOPS_MONITORING_DIR"):
        monkeypatch.setenv(name, str(tmp_path / name.lower()))
    for name in ("DATAOPS_ALERT_WEBHOOK_URL", "DATAOPS_ALERT_EMAIL", "DATAOPS_ALERT_ON_RETRY"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


@pytest.fixture
def receiver():
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(204 if received[-1].get("text", "").startswith("x") else 200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:{}/hook".format(server.server_port), received
    server.shutdown()


def task_context(task_id="dbt_run", try_number=1, max_tries=2):
    ti = SimpleNamespace(
        dag_id="dbt_transform",
        task_id=task_id,
        _try_number=try_number,
        max_tries=max_tries,
        state="failed",
        start_date=NOW,
        end_date=NOW,
        duration=1.0,
        log_url="http://airflow/log",
    )
    return {"dag": SimpleNamespace(dag_id="dbt_transform"), "dag_run": SimpleNamespace(run_id="r1"), "ti": ti}


# ------------------------------------------------------------------ alerting --


def test_alert_written_to_log_when_no_channel_configured():
    alert = alerting.send_alert("Something broke", "details", severity="critical")
    assert alert["delivery"] == {"webhook": "disabled", "email": "disabled", "log": "written"}
    assert alerting.read_alerts()[0]["title"] == "Something broke"


def test_unknown_severity_becomes_critical():
    assert alerting.send_alert("t", severity="nope")["severity"] == "critical"


@pytest.mark.parametrize(
    "fmt,key",
    [("slack", "text"), ("discord", "content"), ("teams", "text"), ("generic", "title")],
)
def test_webhook_payload_formats(monkeypatch, receiver, fmt, key):
    url, received = receiver
    monkeypatch.setenv("DATAOPS_ALERT_WEBHOOK_URL", url)
    monkeypatch.setenv("DATAOPS_ALERT_WEBHOOK_FORMAT", fmt)
    alert = alerting.send_alert("Task failed: dbt_transform.dbt_run", context=task_context())
    assert alert["delivery"]["webhook"] == "sent"
    assert key in received[0]
    assert "dbt_run" in json.dumps(received[0])


def test_webhook_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("DATAOPS_ALERT_WEBHOOK_URL", "http://127.0.0.1:9/unreachable")
    alert = alerting.send_alert("t")
    assert alert["delivery"]["webhook"].startswith("error_")
    assert "127.0.0.1" not in json.dumps(alert["delivery"])  # URL (secret) never echoed


def test_retry_alert_is_warning_and_can_be_disabled(monkeypatch):
    callbacks.on_task_retry(task_context(try_number=1))
    assert alerting.read_alerts()[-1]["severity"] == "warning"
    assert "Attempt 1 of 3" in alerting.read_alerts()[-1]["message"]
    monkeypatch.setenv("DATAOPS_ALERT_ON_RETRY", "false")
    callbacks.on_task_retry(task_context(try_number=2))
    assert len(alerting.read_alerts()) == 1


def test_dag_failure_alerts_only_for_non_task_causes():
    context = {"dag": SimpleNamespace(dag_id="dbt_transform"), "reason": "task_failure"}
    callbacks.on_dag_failure(context)
    assert alerting.read_alerts() == []
    callbacks.on_dag_failure(dict(context, reason="timed_out"))
    assert "timed_out" in alerting.read_alerts()[0]["message"]


def test_sla_callback_alerts():
    callbacks.on_sla_miss(SimpleNamespace(dag_id="dbt_transform"), "", "", [SimpleNamespace(task_id="dbt_docs")], [])
    assert alerting.read_alerts()[0]["title"] == "SLA missed: dbt_transform"


# ---------------------------------------------------------------- monitoring --


def containers(**overrides):
    base = {s: ("running", "healthy") for s in monitoring.REQUIRED_SERVICES}
    base.update(overrides)
    return [{"service": s, "state": st, "health": h, "status": ""} for s, (st, h) in base.items()]


def test_check_services():
    assert monitoring.check_services(containers())["status"] == "ok"
    bad = monitoring.check_services(containers(**{"ge-worker": ("exited", None), "postgres": ("running", "unhealthy")}))
    assert bad["status"] == "critical"
    assert bad["problems"] == ["postgres: unhealthy", "ge-worker: not running"]


def run(run_id, state, hours_ago):
    return {"run_id": run_id, "state": state, "end_date": NOW - timedelta(hours=hours_ago)}


def test_check_pipeline_states():
    assert monitoring.check_pipeline([run("a", "success", 2)], now=NOW)["status"] == "ok"
    assert monitoring.check_pipeline([run("b", "failed", 1), run("a", "success", 2)], now=NOW)["status"] == "critical"
    stale = monitoring.check_pipeline([run("a", "success", 30)], now=NOW, max_age_hours=26)
    assert stale["status"] == "critical" and stale["hours_since_success"] == 30
    assert monitoring.check_pipeline([run("a", "success", 30)], now=NOW, scheduled=False)["status"] == "warning"
    running_after_failure = [{"run_id": "c", "state": "running", "end_date": None}, run("b", "failed", 1)]
    assert monitoring.check_pipeline(running_after_failure, now=NOW)["status"] == "critical"
    assert monitoring.check_pipeline([], now=NOW)["status"] == "warning"


def test_check_metrics_threshold():
    records = [{"dag_id": "dbt_transform", "event": "task_success"}] * 3 + [
        {"dag_id": "dbt_transform", "event": "task_failure"},
        {"dag_id": "other", "event": "task_failure"},
    ]
    assert monitoring.check_metrics(records, min_success_rate=0.8)["status"] == "warning"
    assert monitoring.check_metrics(records, min_success_rate=0.7)["status"] == "ok"
    assert monitoring.check_metrics([], min_success_rate=0.8)["detail"] == "no finished tasks in window"


def test_check_disk(tmp_path):
    assert monitoring.check_disk([tmp_path], min_free_gb=0, warn_free_gb=0)["status"] == "ok"
    assert monitoring.check_disk([tmp_path], min_free_gb=10**9)["status"] == "critical"
    assert monitoring.check_disk(["/does/not/exist"])["status"] == "warning"


def report_with(status):
    return monitoring.build_report([monitoring.result("services", status, "x")], now=NOW)


def test_decide_alert_on_change_only():
    critical, ok = report_with("critical"), report_with("ok")
    assert monitoring.decide_alert(ok, None, now=NOW) is None
    assert monitoring.decide_alert(critical, {"status": "ok"}, now=NOW)[0] == "critical"
    recent = {"status": "critical", "last_alert_utc": (NOW - timedelta(hours=1)).isoformat()}
    assert monitoring.decide_alert(critical, recent, now=NOW) is None
    old = {"status": "critical", "last_alert_utc": (NOW - timedelta(hours=7)).isoformat()}
    assert "still" in monitoring.decide_alert(critical, old, now=NOW)[1]
    assert monitoring.decide_alert(ok, {"status": "critical"}, now=NOW)[0] == "info"


def test_alert_title_lists_failing_checks_and_message_has_details():
    report = monitoring.build_report(
        [
            monitoring.result("services", "critical", "sqlserver: not running"),
            monitoring.result("pipeline", "critical", "last run x failed"),
            monitoring.result("disk", "ok", "200 GB free"),
        ],
        now=NOW,
    )
    severity, title = monitoring.decide_alert(report, {"status": "ok"}, now=NOW)
    assert (severity, title) == ("critical", "DataOps health CRITICAL: services, pipeline")
    assert monitoring.failing_summary(report) == "services=sqlserver: not running; pipeline=last run x failed"


def test_publish_writes_status_and_alerts_once(isolated_dirs):
    first = monitoring.publish(report_with("critical"))
    second = monitoring.publish(report_with("critical"))
    third = monitoring.publish(report_with("ok"))
    assert "alert" in first and "alert" not in second and third["alert"]["severity"] == "info"
    latest = json.loads((isolated_dirs / "dataops_monitoring_dir" / "latest.json").read_text())
    assert latest["status"] == "ok"
    assert len(alerting.read_alerts()) == 2


# ------------------------------------------------------------------ pipeline --


def test_resolve_schedule():
    assert pipeline.resolve_schedule("", "0 6 * * *") == "0 6 * * *"
    assert pipeline.resolve_schedule(" manual ", "0 6 * * *") is None
    assert pipeline.resolve_schedule("@hourly", "0 6 * * *") == "@hourly"


def test_latest_task_summary_picks_newest_attempt(tmp_path):
    folder = tmp_path / "airflow" / pipeline.run_key("ge_data_quality", "r1") / "ge_validate"
    for attempt, status in ((1, "error"), (2, "passed")):
        path = folder / "try-{}-abc".format(attempt)
        path.mkdir(parents=True)
        (path / "task_summary.json").write_text(json.dumps({"attempt": attempt, "status": status}))
    summary, where = pipeline.latest_task_summary("ge_data_quality", "r1", "ge_validate", root=tmp_path)
    assert summary["status"] == "passed" and where.name == "try-2-abc"
    assert pipeline.latest_task_summary("ge_data_quality", "missing", "ge_validate", root=tmp_path) == (None, None)
