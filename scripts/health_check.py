#!/usr/bin/env python3
"""One-command health check of the DataOps stack, run from the repository root.

    python3 scripts/health_check.py                    # human readable table
    python3 scripts/health_check.py --json             # machine readable
    python3 scripts/health_check.py --skip-dbt         # faster, no dbt debug
    python3 scripts/health_check.py --resolve "INC-20261119-01 SQL Server restarted"

Exit code: 0 = healthy, 1 = warning, 2 = critical. Usable in cron, CI smoke
steps and as the first command of every incident (docs/incident_runbook.md).

Only the Python standard library and the Docker CLI are required. Containers
are located by Compose labels, so any project name works (``--project`` or
``COMPOSE_PROJECT_NAME``, default ``dbt_airflow_project``). Credentials are
passed to sqlcmd through the container environment, never printed.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

OK, WARNING, CRITICAL, SKIPPED = "ok", "warning", "critical", "skipped"
RANK = {OK: 0, SKIPPED: 0, WARNING: 1, CRITICAL: 2}
REQUIRED = ("sqlserver", "postgres", "airflow-webserver", "airflow-scheduler", "dbt", "ge-worker")
REPO = Path(__file__).resolve().parents[1]
PIPELINE_DAG = "dbt_transform"
ALERTS = REPO / "airflow/logs/dataops_alerts/alerts.jsonl"
RESET_TITLES = ("DataOps recovered", "Incident resolved")


class Checker:
    def __init__(self, project, airflow_url, timeout):
        self.project = project
        self.airflow_url = airflow_url.rstrip("/")
        self.timeout = timeout
        self.results = []
        self._containers = None

    # ------------------------------------------------------------ helpers --
    def add(self, name, status, detail, hint=""):
        self.results.append({"check": name, "status": status, "detail": detail, "hint": hint})
        return status

    def run(self, args, timeout=None, env=None):
        return subprocess.run(
            args, capture_output=True, text=True, timeout=timeout or self.timeout, env=env, check=False
        )

    def containers(self):
        if self._containers is None:
            out = self.run(
                [
                    "docker",
                    "ps",
                    "-a",
                    "--filter",
                    "label=com.docker.compose.project=" + self.project,
                    "--format",
                    '{{.ID}}\t{{.Label "com.docker.compose.service"}}\t{{.State}}\t{{.Status}}',
                ]
            )
            self._containers = []
            for line in out.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) == 4:
                    self._containers.append(dict(zip(("id", "service", "state", "status"), parts)))
        return self._containers

    def container(self, service):
        for item in self.containers():
            if item["service"] == service and item["state"] == "running":
                return item["id"]
        return None

    def exec_in(self, service, command, timeout=None, env=None):
        cid = self.container(service)
        if cid is None:
            return None
        args = ["docker", "exec"]
        for key in env or {}:
            args += ["-e", key]  # value comes from our environment: never on a command line
        child_env = dict(os.environ, **env) if env else None
        return self.run(args + [cid] + command, timeout=timeout, env=child_env)

    # ------------------------------------------------------------- checks --
    def check_docker(self):
        try:
            result = self.run(["docker", "version", "--format", "{{.Server.Version}}"])
        except (OSError, subprocess.TimeoutExpired) as error:
            return self.add("docker", CRITICAL, type(error).__name__, "Is Docker running? Can this user use it?")
        if result.returncode != 0:
            return self.add("docker", CRITICAL, "daemon not reachable", "systemctl start docker / Docker Desktop")
        return self.add("docker", OK, "server " + result.stdout.strip())

    def check_services(self):
        problems = []
        for service in REQUIRED:
            items = [c for c in self.containers() if c["service"] == service]
            running = [c for c in items if c["state"] == "running"]
            if not running:
                problems.append("{} {}".format(service, items[0]["state"] if items else "missing"))
            elif "(unhealthy)" in running[0]["status"]:
                problems.append(service + " unhealthy")
        if problems:
            return self.add(
                "services",
                CRITICAL,
                ", ".join(problems),
                "docker compose ... up -d <service>; docker compose ... logs --tail 100 <service>",
            )
        return self.add("services", OK, "{}/{} running".format(len(REQUIRED), len(REQUIRED)))

    def check_sqlserver(self):
        password = os.environ.get("SQLSERVER_SA_PASSWORD", "YourStrong@Passw0rd")
        query = "SET NOCOUNT ON; SELECT state_desc FROM sys.databases WHERE name = 'AdventureWorks2014'"
        try:
            result = self.exec_in(
                "sqlserver",
                ["/opt/mssql-tools/bin/sqlcmd", "-S", "localhost", "-U", "sa", "-h", "-1", "-W", "-b", "-Q", query],
                env={"SQLCMDPASSWORD": password},
            )
        except subprocess.TimeoutExpired:
            return self.add("sqlserver", CRITICAL, "query timed out", "docker compose ... logs sqlserver")
        if result is None:
            return self.add("sqlserver", CRITICAL, "container not running", "docker compose ... up -d sqlserver")
        state = result.stdout.strip()
        if result.returncode != 0:
            return self.add("sqlserver", CRITICAL, "login/query failed", "SQL Server still starting? Check SA password")
        if state != "ONLINE":
            return self.add(
                "sqlserver",
                CRITICAL,
                "AdventureWorks2014 " + (state or "missing"),
                "docker compose ... exec sqlserver /tmp/restore_db.sh",
            )
        return self.add("sqlserver", OK, "AdventureWorks2014 ONLINE")

    def check_dbt(self, skip):
        if skip:
            return self.add("dbt", SKIPPED, "--skip-dbt")
        try:
            result = self.exec_in("dbt", ["dbt", "debug"], timeout=max(self.timeout, 120))
        except subprocess.TimeoutExpired:
            return self.add("dbt", CRITICAL, "dbt debug timed out", "SQL Server reachable from dbt container?")
        if result is None:
            return self.add("dbt", CRITICAL, "container not running", "docker compose ... up -d dbt")
        if result.returncode != 0:
            return self.add("dbt", CRITICAL, "dbt debug failed", "check dbt/profiles.yml and the dbt SQL login")
        return self.add("dbt", OK, "dbt debug: all checks passed")

    def airflow_health(self):
        try:
            with urllib.request.urlopen(self.airflow_url + "/health", timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - fall back to inside the container (port not published)
            result = self.exec_in(
                "airflow-webserver", ["curl", "-s", "--max-time", "10", "http://localhost:8080/health"]
            )
            if result is None or result.returncode != 0:
                return None
            try:
                return json.loads(result.stdout)
            except ValueError:
                return None

    def check_airflow(self):
        health = self.airflow_health()
        if health is None:
            return self.add(
                "airflow", CRITICAL, "webserver /health unreachable", "docker compose ... logs airflow-webserver"
            )
        db = health.get("metadatabase", {}).get("status")
        scheduler = health.get("scheduler", {})
        if db != "healthy":
            return self.add("airflow", CRITICAL, "metadata DB " + str(db), "check postgres container")
        if scheduler.get("status") != "healthy":
            return self.add(
                "airflow",
                CRITICAL,
                "scheduler {} (last heartbeat {})".format(
                    scheduler.get("status"), scheduler.get("latest_scheduler_heartbeat")
                ),
                "docker compose ... restart airflow-scheduler",
            )
        return self.add("airflow", OK, "metadata DB and scheduler healthy")

    def airflow_cli(self, *args):
        result = self.exec_in("airflow-scheduler", ["airflow"] + list(args) + ["-o", "json"], timeout=90)
        if result is None or result.returncode != 0:
            return None
        start = result.stdout.find("[")
        try:
            return json.loads(result.stdout[start:]) if start >= 0 else []
        except ValueError:
            return None

    def check_dag_imports(self):
        errors = self.airflow_cli("dags", "list-import-errors")
        if errors is None:
            return self.add("dag_imports", WARNING, "could not query import errors")
        if errors:
            files = ", ".join(sorted({Path(e.get("filepath", "?")).name for e in errors}))
            return self.add("dag_imports", CRITICAL, "import errors in " + files, "airflow dags list-import-errors")
        return self.add("dag_imports", OK, "no DAG import errors")

    def check_last_run(self):
        runs = self.airflow_cli("dags", "list-runs", "-d", PIPELINE_DAG)
        if runs is None:
            return self.add("last_run", WARNING, "could not list runs of " + PIPELINE_DAG)
        finished = [r for r in runs if r.get("state") in ("success", "failed")]
        running = [r for r in runs if r.get("state") in ("running", "queued")]
        suffix = " ({} active)".format(len(running)) if running else ""
        if not finished:
            return self.add("last_run", WARNING, "no finished run" + suffix)
        last = max(finished, key=lambda r: r.get("end_date") or "")
        if last["state"] == "failed":
            return self.add(
                "last_run",
                CRITICAL,
                "{} failed{}".format(last["run_id"], suffix),
                "Airflow UI > dbt_transform > failed task > Logs; runbook section 3",
            )
        return self.add("last_run", OK, "{} success at {}{}".format(last["run_id"], last.get("end_date"), suffix))

    def check_orphans(self):
        """dbt/GX processes left behind by a killed task (docker exec does not stop them)."""
        script = 'for p in /proc/[0-9]*; do tr "\\0" " " < "$p/cmdline" 2>/dev/null; echo; done'
        found = []
        for service, program in (("dbt", "dbt"), ("ge-worker", "run_ge_checkpoints.py")):
            result = self.exec_in(service, ["sh", "-c", script])
            if result is None:
                continue
            for line in result.stdout.splitlines():
                # "dbt run ..." or "python /usr/local/bin/dbt run ..." - not a shell that merely mentions it
                head = [Path(token).name for token in line.split()[:2]]
                if program in head:
                    found.append(service)
        runs = self.airflow_cli("dags", "list-runs", "-d", PIPELINE_DAG, "--state", "running") or []
        if found and not runs:
            return self.add(
                "orphans",
                WARNING,
                "{} dbt/GX process(es) running but no {} run is active".format(len(found), PIPELINE_DAG),
                "runbook 2.5: inspect and kill before clearing/retrying tasks",
            )
        return self.add("orphans", OK, "{} dbt/GX process(es), {} active run(s)".format(len(found), len(runs)))

    def check_monitoring(self):
        path = REPO / "airflow/logs/dataops_monitoring/latest.json"
        try:
            latest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self.add("monitoring", WARNING, "no monitoring report yet", "is dataops_monitoring unpaused?")
        age = datetime.now(timezone.utc) - datetime.fromisoformat(latest["timestamp_utc"])
        if age > timedelta(hours=1):
            return self.add(
                "monitoring",
                WARNING,
                "last report {:.0f} min old".format(age.total_seconds() / 60),
                "monitor DAG stuck?",
            )
        status = latest.get("status", "?")
        level = {"ok": OK, "warning": WARNING}.get(status, CRITICAL)
        return self.add(
            "monitoring", level, "dataops_monitoring says {} ({:.0f} min ago)".format(status, age.total_seconds() / 60)
        )

    def check_alerts(self):
        """Critical alerts in 24 h; WARN only if one is still unresolved (no later recovery)."""
        path = ALERTS
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        total, open_alerts, last = 0, 0, None
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    alert = json.loads(line)
                    if datetime.fromisoformat(alert["timestamp_utc"]) < since:
                        continue
                except (ValueError, KeyError):
                    continue
                if alert.get("severity") == "critical":
                    total, open_alerts, last = total + 1, open_alerts + 1, alert.get("title")
                elif alert.get("title", "").startswith(RESET_TITLES):
                    open_alerts = 0
        if open_alerts:
            return self.add(
                "alerts_24h",
                WARNING,
                "{} critical alert(s) since last recovery; last: {}".format(open_alerts, last),
                "follow docs/incident_runbook.md, then: health_check.py --resolve '<incident note>'",
            )
        if total:
            return self.add("alerts_24h", OK, "{} critical alert(s) in 24 h, all followed by recovery".format(total))
        return self.add("alerts_24h", OK, "no critical alerts in 24 h")

    def check_disk(self):
        free_gb = shutil.disk_usage(REPO).free / 1024**3
        if free_gb < 2:
            return self.add(
                "disk", CRITICAL, "{:.1f} GB free".format(free_gb), "clean old evidence/logs, docker system prune"
            )
        if free_gb < 5:
            return self.add("disk", WARNING, "{:.1f} GB free".format(free_gb))
        return self.add("disk", OK, "{:.1f} GB free".format(free_gb))


def resolve(note):
    """Close open incidents: append an info alert that resets the alerts_24h check."""
    record = {
        "event": "alert",
        "severity": "info",
        "title": "Incident resolved: " + note,
        "message": "Closed manually with scripts/health_check.py --resolve",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "resolved_by": os.environ.get("USER", "unknown"),
    }
    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True) + "\n")
    print("Recorded: " + record["title"])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=os.environ.get("COMPOSE_PROJECT_NAME", "dbt_airflow_project"))
    parser.add_argument("--airflow-url", default=os.environ.get("AIRFLOW_URL", "http://localhost:8080"))
    parser.add_argument("--skip-dbt", action="store_true", help="skip dbt debug (saves ~5 s)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--resolve", metavar="NOTE", help="record that open incidents are resolved, then check")
    args = parser.parse_args()
    if args.resolve:
        resolve(args.resolve)

    checker = Checker(args.project, args.airflow_url, args.timeout)
    if checker.check_docker() == OK:
        checker.check_services()
        checker.check_sqlserver()
        checker.check_dbt(args.skip_dbt)
        checker.check_airflow()
        checker.check_dag_imports()
        checker.check_last_run()
        checker.check_orphans()
    checker.check_monitoring()
    checker.check_alerts()
    checker.check_disk()

    overall = max((r["status"] for r in checker.results), key=lambda s: RANK[s])
    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "project": args.project,
        "status": overall,
        "checks": checker.results,
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        icons = {OK: "OK  ", WARNING: "WARN", CRITICAL: "FAIL", SKIPPED: "SKIP"}
        print("DataOps health check - project {} - {}".format(args.project, report["timestamp_utc"]))
        for r in checker.results:
            print("[{}] {:<12} {}".format(icons[r["status"]], r["check"], r["detail"]))
            if r["status"] in (WARNING, CRITICAL) and r["hint"]:
                print("       {:<12} -> {}".format("", r["hint"]))
        print("OVERALL: {}".format(overall.upper()))
    return RANK[overall] if overall != SKIPPED else 0


if __name__ == "__main__":
    sys.exit(main())
