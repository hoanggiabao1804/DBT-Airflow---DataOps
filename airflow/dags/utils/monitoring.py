"""Health checks used by the ``dataops_monitoring`` DAG.

Each check returns a dict ``{"check", "status", "detail", ...}`` where status is
``ok``, ``warning`` or ``critical``. The functions take plain inputs (lists of
containers, run records, metric records) so they are unit-testable without
Docker or Airflow; the thin collectors that talk to Docker/Airflow are kept
separate (``docker_containers``, ``pipeline_runs``).
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess

from utils.alerting import send_alert
from utils.logging_utils import append_jsonl, log_event, summarize_metrics

OK, WARNING, CRITICAL = "ok", "warning", "critical"
_RANK = {OK: 0, WARNING: 1, CRITICAL: 2}

REQUIRED_SERVICES = ("sqlserver", "postgres", "airflow-webserver", "airflow-scheduler", "dbt", "ge-worker")
DEFAULT_STATUS_DIR = "/opt/airflow/logs/dataops_monitoring"


def result(check, status, detail, **extra):
    record = {"check": check, "status": status, "detail": detail}
    record.update(extra)
    return record


def worst(statuses):
    return max(statuses, key=lambda status: _RANK.get(status, 2), default=OK)


def env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


# ----------------------------------------------------------------- services ---


def docker_containers(project):
    """List containers of a Compose project as dicts: service, state, health."""
    output = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "label=com.docker.compose.project=" + project,
            "--format",
            '{{.Label "com.docker.compose.service"}}\t{{.State}}\t{{.Status}}',
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout
    containers = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        service, state, status = parts
        health = "unhealthy" if "(unhealthy)" in status else "healthy" if "(healthy)" in status else None
        containers.append({"service": service, "state": state, "health": health, "status": status})
    return containers


def check_services(containers, required=REQUIRED_SERVICES):
    """Every required service has a running, not-unhealthy container."""
    problems = []
    by_service = {}
    for container in containers:
        by_service.setdefault(container["service"], []).append(container)
    for service in required:
        running = [c for c in by_service.get(service, []) if c["state"] == "running"]
        if not running:
            problems.append("{}: not running".format(service))
        elif any(c["health"] == "unhealthy" for c in running):
            problems.append("{}: unhealthy".format(service))
    if problems:
        return result("services", CRITICAL, "; ".join(problems), problems=problems)
    return result("services", OK, "{} services running".format(len(required)))


# ----------------------------------------------------------------- pipeline ---


def check_pipeline(runs, now=None, max_age_hours=26.0, scheduled=True):
    """Judge the main pipeline from its recent DAG runs (newest first).

    ``runs`` items: {"run_id", "state", "end_date" (datetime or None)}.
    * last finished run failed                 -> critical
    * no success within ``max_age_hours``      -> warning (critical if scheduled and never succeeded)
    """
    now = now or datetime.now(timezone.utc)
    finished = [run for run in runs if run.get("state") in ("success", "failed")]
    successes = [run for run in finished if run["state"] == "success" and run.get("end_date")]
    running = [run for run in runs if run.get("state") in ("running", "queued")]
    extra = {"running_runs": len(running)}
    if successes:
        age = (now - successes[0]["end_date"]).total_seconds() / 3600
        extra.update(last_success_run_id=successes[0]["run_id"], hours_since_success=round(age, 2))
    if finished and finished[0]["state"] == "failed":
        return result("pipeline", CRITICAL, "last run {} failed".format(finished[0]["run_id"]), **extra)
    if not successes:
        status = CRITICAL if scheduled and finished else WARNING
        return result("pipeline", status, "no successful run recorded", **extra)
    if extra["hours_since_success"] > max_age_hours:
        status = WARNING if not scheduled else CRITICAL
        return result(
            "pipeline",
            status,
            "last success {:.1f} h ago (limit {:.0f} h)".format(extra["hours_since_success"], max_age_hours),
            **extra
        )
    return result("pipeline", OK, "last success {:.1f} h ago".format(extra["hours_since_success"]), **extra)


def check_metrics(records, min_success_rate=0.8, dag_id="dbt_transform"):
    """Task success rate of ``dag_id`` over the supplied (already time-filtered) records."""
    summary = summarize_metrics(record for record in records if record.get("dag_id") == dag_id)
    rate = summary["task_success_rate"]
    extra = {key: summary[key] for key in ("task_success", "task_failure", "task_retry", "task_success_rate")}
    if rate is None:
        return result("metrics", OK, "no finished tasks in window", **extra)
    if rate < min_success_rate:
        return result("metrics", WARNING, "task success rate {:.0%} < {:.0%}".format(rate, min_success_rate), **extra)
    return result("metrics", OK, "task success rate {:.0%}".format(rate), **extra)


# --------------------------------------------------------------------- disk ---


def check_disk(paths, min_free_gb=2.0, warn_free_gb=5.0):
    """Free space on the volumes holding logs/evidence."""
    measured = []
    for path in paths:
        try:
            measured.append((shutil.disk_usage(path).free / 1024**3, str(path)))
        except OSError:
            continue
    if not measured:
        return result("disk", WARNING, "no path could be inspected")
    free_gb, path = min(measured)
    extra = {"path": path, "free_gb": round(free_gb, 2)}
    if free_gb < min_free_gb:
        return result("disk", CRITICAL, "{:.1f} GB free on {}".format(free_gb, path), **extra)
    if free_gb < warn_free_gb:
        return result("disk", WARNING, "{:.1f} GB free on {}".format(free_gb, path), **extra)
    return result("disk", OK, "{:.1f} GB free".format(free_gb), **extra)


# ------------------------------------------------------------------- report ---


def status_dir():
    return Path(os.environ.get("DATAOPS_MONITORING_DIR", DEFAULT_STATUS_DIR))


def load_previous(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def build_report(checks, now=None):
    now = now or datetime.now(timezone.utc)
    return {
        "timestamp_utc": now.isoformat(),
        "status": worst(check["status"] for check in checks),
        "checks": checks,
    }


def decide_alert(report, previous, repeat_after=timedelta(hours=6), now=None):
    """Alert on state *changes* (and re-alert a persisting problem every ``repeat_after``).

    Returns (severity, title) or None. Avoids paging every 30 minutes for the
    same incident while still announcing recovery.
    """
    now = now or datetime.now(timezone.utc)
    current = report["status"]
    before = (previous or {}).get("status", OK)
    if current == OK:
        return ("info", "DataOps recovered: all checks OK") if before != OK else None
    if current != before:
        return current, "DataOps health {}: {}".format(current.upper(), failing_checks(report))
    last_alert = (previous or {}).get("last_alert_utc")
    try:
        overdue = last_alert is None or now - datetime.fromisoformat(last_alert) >= repeat_after
    except ValueError:
        overdue = True
    if overdue:
        return current, "DataOps health still {}: {}".format(current.upper(), failing_checks(report))
    return None


def failing_checks(report):
    """Short form for alert titles: names of the checks that are not OK."""
    return ", ".join(check["check"] for check in report["checks"] if check["status"] != OK)


def failing_summary(report):
    return "; ".join(
        "{}={}".format(check["check"], check["detail"]) for check in report["checks"] if check["status"] != OK
    )


def publish(report, context=None):
    """Write latest.json + history, send an alert when decide_alert says so."""
    folder = status_dir()
    previous = load_previous(folder / "latest.json")
    decision = decide_alert(report, previous)
    report = dict(report)
    report["last_alert_utc"] = (previous or {}).get("last_alert_utc")
    if decision:
        severity, title = decision
        alert = send_alert(title, failing_summary(report) or "All checks OK", severity=severity, context=context)
        report["last_alert_utc"] = alert["timestamp_utc"]
        report["alert"] = {"severity": severity, "title": title, "delivery": alert["delivery"]}
    folder.mkdir(parents=True, exist_ok=True)
    tmp = folder / "latest.json.tmp"
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    tmp.replace(folder / "latest.json")
    append_jsonl(folder / "history.jsonl", report)
    log_event("health_report", context, status=report["status"], alerted=bool(decision))
    return report
