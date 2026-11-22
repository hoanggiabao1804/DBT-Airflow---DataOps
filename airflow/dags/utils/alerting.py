"""Failure notifications for DataOps DAGs.

Channels (all optional except the alert log):

1. **Alert log** - always on. One JSON line per alert in
   ``$DATAOPS_ALERT_DIR/alerts.jsonl``. This is the audit trail used by the
   runbook, the monitoring DAG and the health check, and it works offline.
2. **Webhook** - set ``DATAOPS_ALERT_WEBHOOK_URL``. ``DATAOPS_ALERT_WEBHOOK_FORMAT``
   selects the payload: ``slack`` (also Mattermost/Rocket.Chat), ``discord``,
   ``teams`` or ``generic`` (the full alert record as JSON, default).
3. **Email** - set ``DATAOPS_ALERT_EMAIL`` (comma separated) *and* configure
   Airflow SMTP. Uses ``airflow.utils.email.send_email``.

Secrets (webhook URL) come from the environment only and are never logged.
A notification failure is logged and recorded, but never raised: a broken
Slack integration must not change the state of the data pipeline.
"""

import json
import os
from pathlib import Path
import urllib.error
import urllib.request

from utils.logging_utils import append_jsonl, build_event, log_event

DEFAULT_ALERT_DIR = "/opt/airflow/logs/dataops_alerts"
ALERTS_FILENAME = "alerts.jsonl"
SEVERITIES = ("info", "warning", "critical")
WEBHOOK_TIMEOUT_SECONDS = 10
_ICONS = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


def alert_dir():
    return Path(os.environ.get("DATAOPS_ALERT_DIR", DEFAULT_ALERT_DIR))


def alerts_path():
    return alert_dir() / ALERTS_FILENAME


def environment_name():
    return os.environ.get("AIRFLOW_ENV") or os.environ.get("DATAOPS_ENV") or "development"


def format_text(alert):
    """Human readable, single message used by chat channels and email."""
    lines = [
        "{} [{}] {}".format(_ICONS.get(alert["severity"], ""), alert["severity"].upper(), alert["title"]).strip(),
        "Environment: {}".format(alert.get("environment")),
    ]
    for label, key in (
        ("DAG", "dag_id"),
        ("Task", "task_id"),
        ("Run", "run_id"),
        ("Attempt", "try_number"),
        ("Error", "exception_type"),
    ):
        if alert.get(key) is not None:
            lines.append("{}: {}".format(label, alert[key]))
    if alert.get("message"):
        lines.append(alert["message"])
    if alert.get("log_url"):
        lines.append("Log: {}".format(alert["log_url"]))
    if alert.get("runbook"):
        lines.append("Runbook: {}".format(alert["runbook"]))
    return "\n".join(lines)


def build_payload(alert, fmt):
    text = format_text(alert)
    if fmt == "slack":
        return {"text": text}
    if fmt == "discord":
        return {"content": text[:1900]}
    if fmt == "teams":
        return {"@type": "MessageCard", "@context": "https://schema.org/extensions", "text": text.replace("\n", "<br>")}
    return dict(alert, text=text)


def _post_json(url, payload):
    data = json.dumps(payload, default=str).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json", "User-Agent": "dataops-alerting/1.0"}
    )
    with urllib.request.urlopen(request, timeout=WEBHOOK_TIMEOUT_SECONDS) as response:  # nosec - URL from operator env
        return response.status


def send_webhook(alert):
    url = os.environ.get("DATAOPS_ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return "disabled"
    fmt = os.environ.get("DATAOPS_ALERT_WEBHOOK_FORMAT", "generic").strip().lower()
    try:
        status = _post_json(url, build_payload(alert, fmt))
        return "sent" if 200 <= status < 300 else "http_{}".format(status)
    except urllib.error.HTTPError as error:
        return "http_{}".format(error.code)
    except Exception as error:  # noqa: BLE001
        # Do not include the URL: chat webhooks embed their secret token in it.
        return "error_{}".format(type(error).__name__)


def send_email_alert(alert):
    recipients = [item.strip() for item in os.environ.get("DATAOPS_ALERT_EMAIL", "").split(",") if item.strip()]
    if not recipients:
        return "disabled"
    try:
        from airflow.utils.email import send_email  # imported lazily: optional at runtime

        body = "<pre>{}</pre>".format(format_text(alert).replace("<", "&lt;"))
        send_email(
            to=recipients, subject="[DataOps][{}] {}".format(alert["severity"], alert["title"]), html_content=body
        )
        return "sent"
    except Exception as error:  # noqa: BLE001
        return "error_{}".format(type(error).__name__)


def send_alert(title, message="", severity="critical", context=None, dag_level=False, **extra):
    """Record an alert and fan it out to the configured channels.

    Returns the alert record including the delivery status of every channel,
    so callers (and tests) can see exactly what happened.
    """
    severity = severity if severity in SEVERITIES else "critical"
    alert = build_event(
        "alert",
        context,
        dag_level=dag_level,
        title=title,
        message=message,
        severity=severity,
        environment=environment_name(),
        runbook=os.environ.get("DATAOPS_RUNBOOK_URL", "docs/incident_runbook.md"),
        **extra
    )
    alert["delivery"] = {"webhook": send_webhook(alert), "email": send_email_alert(alert)}
    alert["delivery"]["log"] = "written" if append_jsonl(alerts_path(), alert) else "error"
    level = 40 if severity == "critical" else 30 if severity == "warning" else 20
    log_event(
        "alert_sent",
        context,
        level=level,
        dag_level=dag_level,
        title=title,
        severity=severity,
        delivery=alert["delivery"],
    )
    return alert


def read_alerts(path=None):
    path = Path(path) if path else alerts_path()
    if not path.is_file():
        return []
    alerts = []
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                alerts.append(json.loads(line))
            except ValueError:
                continue
    return alerts
