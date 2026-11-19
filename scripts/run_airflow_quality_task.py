"""Execute one Airflow quality step in the existing dbt or isolated GX worker.

Only the Python standard library is needed in Airflow. Native nonzero exit codes
are preserved; missing/inconsistent success artifacts are execution errors (2).
Connection credentials remain inside the mounted dbt profile, never CLI arguments.

Cancellation: when Airflow kills the task (timeout, mark failed, clear) it sends
SIGTERM to the process group. Stopping the local ``docker exec`` client does not
stop the process inside the container, so every command is tagged with
``DATAOPS_PROCESS_MARKER`` and, on SIGTERM, processes carrying that marker are
terminated inside the container before the runner exits (status ``killed``).
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import uuid


class Terminated(Exception):
    """Raised from the SIGTERM handler so cleanup runs in normal control flow."""


def _on_sigterm(signum, frame):
    raise Terminated(signum)


# Kill only processes whose environment holds this run's marker. The helper shell
# itself is started without the marker, so it never kills itself.
KILL_MARKED = (
    "for p in /proc/[0-9]*; do "
    'if tr "\\0" "\\n" < "$p/environ" 2>/dev/null | grep -qx "DATAOPS_PROCESS_MARKER=$1"; then '
    'kill -TERM "${p#/proc/}" 2>/dev/null && echo "${p#/proc/}"; fi; done'
)


def kill_marked(container, marker):
    """Terminate in-container processes tagged with ``marker``; return how many were signalled."""
    result = subprocess.run(
        ["docker", "exec", container, "sh", "-c", KILL_MARKED, "kill-marked", marker],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return len(result.stdout.split())


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def find_container(project, service):
    """Resolve exactly one running Compose service, independent of directory name."""
    result = subprocess.run(
        [
            "docker",
            "ps",
            "--filter",
            "label=com.docker.compose.project=" + project,
            "--filter",
            "label=com.docker.compose.service=" + service,
            "--filter",
            "label=com.docker.compose.oneoff=False",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    identifiers = result.stdout.split()
    if len(identifiers) != 1:
        raise RuntimeError("Expected exactly one running Compose service: " + service)
    return identifiers[0]


def run_logged(command, output):
    # Raw dbt/GX diagnostics remain local. Airflow logs receive aggregate status only.
    with output.open("w", encoding="utf-8") as stream:
        process = subprocess.Popen(command, stdout=stream, stderr=subprocess.STDOUT)
        try:
            return process.wait()
        except Terminated:
            process.terminate()
            raise


def execute(action):
    context = {key: os.environ["DATAOPS_" + key.upper()] for key in ("dag_id", "run_id", "task_id")}
    project = os.environ["DATAOPS_COMPOSE_PROJECT"]
    target = os.environ.get("DATAOPS_DBT_TARGET", "dev")
    schema = os.environ.get("DATAOPS_GE_SCHEMA", "silver")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", target) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
        raise ValueError("Invalid target or schema")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", context["task_id"]):
        raise ValueError("Invalid task ID")
    attempt = int(os.environ.get("DATAOPS_TRY_NUMBER", "1"))
    run_key = hashlib.sha256((context["dag_id"] + "\n" + context["run_id"]).encode()).hexdigest()[:20]
    relative = Path("airflow") / run_key / context["task_id"] / ("try-{}-{}".format(attempt, uuid.uuid4().hex))
    evidence = Path(os.environ.get("DATAOPS_EVIDENCE_ROOT", "/opt/airflow/quality_evidence")) / relative
    evidence.mkdir(parents=True, exist_ok=False)
    summary = dict(
        context,
        action=action,
        attempt=attempt,
        target=target,
        schema=schema,
        started_at_utc=utc_now(),
        status="error",
        exit_code=2,
        native_exit_code=None,
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    )
    write_json(evidence / "task_summary.json", summary)
    marker = uuid.uuid4().hex
    container = None
    signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        service = "ge-worker" if action == "ge" else "dbt"
        container = find_container(project, service)
        if action == "ge":
            command = [
                "docker",
                "exec",
                "-e",
                "DATAOPS_PROCESS_MARKER=" + marker,
                container,
                "python",
                "/workspace/scripts/run_ge_checkpoints.py",
                "--target",
                target,
                "--schema",
                schema,
                "--output-dir",
                "/evidence/" + relative.as_posix() + "/ge",
            ]
        else:
            dbt_relative = Path("target") / relative
            command = [
                "docker",
                "exec",
                "-w",
                "/usr/app/dbt",
                "-e",
                "DBT_TARGET_PATH=" + dbt_relative.as_posix(),
                "-e",
                "DBT_LOG_PATH=" + (dbt_relative / "logs").as_posix(),
                "-e",
                "DBT_USE_COLORS=false",
                "-e",
                "DATAOPS_PROCESS_MARKER=" + marker,
                container,
                "dbt",
            ]
            command += ["docs", "generate"] if action == "docs" else [action]
            if action != "deps":
                command += ["--target", target]
        native_exit = run_logged(command, evidence / "stdout.log")
        summary.update(
            native_exit_code=native_exit, exit_code=native_exit, status="passed" if native_exit == 0 else "failed"
        )
        if action == "ge":
            ge_result = json.loads((evidence / "ge" / "summary.json").read_text(encoding="utf-8"))
            summary["ge_status"] = ge_result["status"]
            summary["ge_expectations"] = sum(
                item["statistics"]["evaluated_expectations"] for item in ge_result["validations"]
            )
            if native_exit != ge_result["exit_code"]:
                raise RuntimeError("GX process and validation exit codes disagree")
            summary["status"] = ge_result["status"]
            if native_exit == 0 and (
                ge_result["status"] != "passed"
                or len(ge_result["validations"]) != 2
                or not all(item["success"] for item in ge_result["validations"])
            ):
                raise RuntimeError("GX did not pass both checkpoints")
        elif action != "deps":
            source = Path("/opt/airflow/dbt") / dbt_relative
            filenames = ["manifest.json"]
            filenames += ["catalog.json", "index.html"] if action == "docs" else ["run_results.json"]
            for filename in filenames:
                artifact = source / filename
                if artifact.is_file():
                    shutil.copyfile(artifact, evidence / filename)
                elif native_exit == 0:
                    raise RuntimeError("dbt succeeded without required artifact: " + filename)
            if action in ("run", "test") and (evidence / "run_results.json").is_file():
                results = json.loads((evidence / "run_results.json").read_text(encoding="utf-8"))["results"]
                counts = {}
                for result in results:
                    counts[result["status"]] = counts.get(result["status"], 0) + 1
                summary["dbt_results"] = counts
                if native_exit == 0 and (not results or any(key not in ("success", "pass") for key in counts)):
                    raise RuntimeError("dbt returned zero without all selected nodes passing")
    except Terminated:
        # Airflow is cancelling this task: stop the work inside the container too.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        killed = kill_marked(container, marker) if container else 0
        summary.update(status="killed", exit_code=143, error_type="Terminated", killed_container_processes=killed)
    except Exception as error:
        # Do not publish subprocess commands, connection strings or unexpected row data.
        summary.update(status="error", exit_code=2, error_type=type(error).__name__)
    finally:
        summary["finished_at_utc"] = utc_now()
        write_json(evidence / "task_summary.json", summary)
    print(
        "{}: {}, native exit {}, final exit {}. Evidence: {}".format(
            context["task_id"], summary["status"], summary["native_exit_code"], summary["exit_code"], evidence
        ),
        flush=True,
    )
    return summary["exit_code"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("deps", "run", "test", "ge", "docs"))
    args = parser.parse_args()
    try:
        return execute(args.action)
    except Exception as error:
        print(
            "Quality task could not start ({}); check Compose/env and evidence permissions.".format(
                type(error).__name__
            ),
            flush=True,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
