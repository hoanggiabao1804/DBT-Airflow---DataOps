"""Exercise real Airflow GE/docs tasks against isolated SQL Server fixtures.

Run inside the quality Airflow scheduler after metadata migration. The verifier
deep-copies the production DAG's GE/docs operators, changes only the fixture
schema and retry count, and uses Airflow's DAG.test() dependency processing. It
does not run dbt models or modify Silver; the valid case runs real dbt docs.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import subprocess
import sys
from threading import Thread
import uuid

from airflow.models import DagBag

from run_airflow_quality_task import find_container

PREFIX = "FIXTURE_EVENT "
CHAIN = ("dbt_deps", "dbt_run", "dbt_test", "ge_validate", "dbt_docs")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def ge_worker():
    project = os.environ.get("DATAOPS_COMPOSE_PROJECT")
    if not project:
        raise RuntimeError("DATAOPS_COMPOSE_PROJECT is required")
    return find_container(project, "ge-worker")


class FixtureServer:
    """Keep fixture ownership in one process until a verified cleanup response."""

    def __init__(self, container, target):
        self.process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                container,
                "python",
                "/workspace/scripts/manage_airflow_fixtures.py",
                "--target",
                target,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.events = Queue()
        self.closed = False
        Thread(target=self._read, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                if line.startswith(PREFIX):
                    payload = line.removeprefix(PREFIX)
                    self.events.put(json.loads(payload))
        finally:
            self.events.put({"event": "eof"})

    def receive(self, expected):
        try:
            event = self.events.get(timeout=120)
        except Empty as error:
            raise RuntimeError("Fixture server timed out") from error
        if event["event"] != expected:
            raise RuntimeError("Unexpected fixture server event: " + event["event"])
        return event

    def request(self, action):
        self.process.stdin.write(json.dumps({"action": action}) + "\n")
        self.process.stdin.flush()
        return self.receive("loaded")

    def close(self):
        if self.closed:
            raise RuntimeError("Fixture server already closed")
        self.closed = True
        try:
            if self.process.poll() is None:
                self.process.stdin.write('{"action":"cleanup"}\n')
                self.process.stdin.flush()
                self.process.stdin.close()
            # A preceding setup error may be followed by the cleanup event.
            while True:
                event = self.events.get(timeout=120)
                if event["event"] in ("closed", "eof"):
                    break
            code = self.process.wait(timeout=120)
            return {"cleanup_verified": event.get("cleanup_verified", False), "fixture_process_exit_code": code}
        except Exception:
            # EOF tells the owner to clean up even when the control protocol fails.
            if not self.process.stdin.closed:
                self.process.stdin.close()
            raise


def check_production_chain(dag):
    if set(dag.task_ids) != set(CHAIN):
        raise AssertionError("Unexpected production task inventory")
    for index, name in enumerate(CHAIN):
        task = dag.get_task(name)
        expected_upstream = {CHAIN[index - 1]} if index else set()
        expected_downstream = {CHAIN[index + 1]} if index + 1 < len(CHAIN) else set()
        if task.upstream_task_ids != expected_upstream or task.downstream_task_ids != expected_downstream:
            raise AssertionError("Unexpected production task dependency")
        if task.trigger_rule != "all_success":
            raise AssertionError("Every production task must require upstream success")


def read_attempt(root, task_id, required=True):
    attempts = list((root / task_id).glob("try-*/task_summary.json"))
    if len(attempts) != int(required):
        raise AssertionError("Unexpected number of task attempts")
    if not required:
        return None, None
    path = attempts[0]
    return path, json.loads(path.read_text(encoding="utf-8"))


def run_case(dag, name, schema, target, expected_exit, fixture, output, evidence_root):
    case_dir = output / name
    case_dir.mkdir()
    subset = dag.partial_subset(
        task_ids_or_regex=["ge_validate", "dbt_docs"], include_upstream=False, include_downstream=False
    )
    subset.dag_id = "quality_contract_" + name + "_" + uuid.uuid4().hex
    for task in subset.tasks:
        task.retries = 0
        task.env["DATAOPS_DBT_TARGET"] = target
    subset.get_task("ge_validate").env["DATAOPS_GE_SCHEMA"] = schema
    dag_run = subset.test(execution_date=datetime.now(timezone.utc))
    states = {task.task_id: task.state for task in dag_run.get_task_instances()}
    expected_states = {
        "ge_validate": "success" if expected_exit == 0 else "failed",
        "dbt_docs": "success" if expected_exit == 0 else "upstream_failed",
    }
    run_hash = hashlib.sha256((subset.dag_id + "\n" + dag_run.run_id).encode()).hexdigest()[:20]
    attempt_root = evidence_root / "airflow" / run_hash
    ge_path, ge_task = read_attempt(attempt_root, "ge_validate")
    docs_path, docs_task = read_attempt(attempt_root, "dbt_docs", required=expected_exit == 0)
    ge_summary_path = ge_path.parent / "ge" / "summary.json"
    ge_summary = json.loads(ge_summary_path.read_text(encoding="utf-8"))
    checks = [check for validation in ge_summary["validations"] for check in validation["checks"]]
    actual_failures = {check["rule_id"]: check.get("unexpected_count") for check in checks if not check["success"]}
    expected_status = {0: "passed", 1: "failed", 2: "error"}[expected_exit]
    matched = (
        states == expected_states
        and dag_run.state == ("success" if expected_exit == 0 else "failed")
        and ge_task["native_exit_code"] == expected_exit
        and ge_task["exit_code"] == expected_exit
        and ge_summary["exit_code"] == expected_exit
        and ge_summary["status"] == expected_status
        and ge_summary["schema"] == schema
    )
    if expected_exit != 2:
        observed_rows = {
            check["rule_id"]: check.get("observed_value")
            for check in checks
            if check["rule_id"] in fixture["expected_rows"]
        }
        matched = matched and (
            len(checks) == 40
            and len({check["rule_id"] for check in checks}) == 40
            and actual_failures == fixture["expected_failures"]
            and observed_rows == fixture["expected_rows"]
        )
    if docs_task is not None:
        matched = matched and docs_task["native_exit_code"] == 0 and docs_task["exit_code"] == 0
    for source, destination in (
        (ge_path, "ge_task_summary.json"),
        (ge_summary_path, "ge_summary.json"),
        (docs_path, "docs_task_summary.json"),
    ):
        if source is not None:
            shutil.copyfile(source, case_dir / destination)
    assertion = {
        "case": name,
        "dag_id": subset.dag_id,
        "run_id": dag_run.run_id,
        "airflow_dag_state": dag_run.state,
        "expected_task_states": expected_states,
        "actual_task_states": states,
        "expected_exit_code": expected_exit,
        "actual_native_exit_code": ge_task["native_exit_code"],
        "ge_status": ge_summary["status"],
        "checks_evaluated": len(checks),
        "expected_failures": fixture.get("expected_failures"),
        "actual_failures": actual_failures,
        "downstream_docs_executed": docs_task is not None,
        "attempt_evidence_relative_path": str(attempt_root.relative_to(evidence_root)),
        "matched": bool(matched),
    }
    write_json(case_dir / "assertion.json", assertion)
    return assertion


def check_repeated_attempt(case, schema, target, output, evidence_root):
    """Repeat a failed helper context; evidence from the first attempt must survive."""
    root = evidence_root / case["attempt_evidence_relative_path"] / "ge_validate"
    before = {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }
    old_attempts = set(root.glob("try-*/task_summary.json"))
    previous = json.loads(next(iter(old_attempts)).read_text(encoding="utf-8"))
    environment = dict(os.environ)
    environment.update(
        DATAOPS_DAG_ID=case["dag_id"],
        DATAOPS_RUN_ID=case["run_id"],
        DATAOPS_TASK_ID="ge_validate",
        DATAOPS_TRY_NUMBER=str(previous["attempt"]),
        DATAOPS_DBT_TARGET=target,
        DATAOPS_GE_SCHEMA=schema,
    )
    process = subprocess.run(
        [sys.executable, str(Path(__file__).with_name("run_airflow_quality_task.py")), "ge"],
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
        timeout=300,
    )
    new_attempts = set(root.glob("try-*/task_summary.json")) - old_attempts
    unchanged = all(
        (root / name).is_file() and hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
        for name, digest in before.items()
    )
    matched = process.returncode == 1 and len(new_attempts) == 1 and unchanged
    result = {
        "case": "repeat_failed_attempt",
        "execution_method": "real helper with identical DAG/run/task/try context",
        "native_exit_code": process.returncode,
        "new_attempt_directories": len(new_attempts),
        "previous_evidence_unchanged": unchanged,
        "previous_evidence_sha256": before,
        "matched": bool(matched),
    }
    destination = output / "repeat_failed_attempt"
    destination.mkdir()
    if len(new_attempts) == 1:
        new_path = next(iter(new_attempts))
        latest = json.loads(new_path.read_text(encoding="utf-8"))
        ge_path = new_path.parent / "ge" / "summary.json"
        ge_result = json.loads(ge_path.read_text(encoding="utf-8"))
        result["matched"] = bool(
            matched
            and latest["native_exit_code"] == 1
            and latest["exit_code"] == 1
            and latest["attempt"] == previous["attempt"]
            and ge_result["status"] == "failed"
            and ge_result["schema"] == schema
        )
        shutil.copyfile(new_path, destination / "ge_task_summary.json")
        shutil.copyfile(ge_path, destination / "ge_summary.json")
    write_json(destination / "assertion.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dag-file", type=Path, default=Path("/opt/airflow/dags/dbt_dag.py"))
    parser.add_argument("--dag-id", default="dbt_transform")
    parser.add_argument("--target", default=os.environ.get("DATAOPS_DBT_TARGET", "dev"))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    evidence_root = Path(os.environ.get("DATAOPS_EVIDENCE_ROOT", "/opt/airflow/quality_evidence"))
    summary = {
        "started_at_utc": utc_now(),
        "status": "running",
        "contracts": [],
        "cleanup_verified": False,
        "execution_method": "Airflow DAG.test with actual GE/docs operators; isolated fixture schema; retries=0",
        "full_production_dag_executed": False,
        "production_dag_sha256": hashlib.sha256(args.dag_file.read_bytes()).hexdigest(),
        "verifier_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_manager_sha256": hashlib.sha256(
            Path(__file__).with_name("manage_airflow_fixtures.py").read_bytes()
        ).hexdigest(),
    }
    write_json(output / "summary.json", summary)
    fixtures = None
    try:
        summary["last_operation"] = "import_and_check_production_dag"
        dag_bag = DagBag(dag_folder=str(args.dag_file), include_examples=False, safe_mode=False)
        if dag_bag.import_errors or args.dag_id not in dag_bag.dags:
            raise RuntimeError("Production DAG did not import cleanly")
        dag = dag_bag.dags[args.dag_id]
        check_production_chain(dag)
        summary["production_task_chain"] = list(CHAIN)
        summary["last_operation"] = "start_fixture_server"
        fixtures = FixtureServer(ge_worker(), args.target)
        ready = fixtures.receive("ready")
        summary["fixture_schema"] = ready["schema"]
        for name, action, expected_exit in (
            ("valid_data", "load_valid", 0),
            ("invalid_data", "load_invalid", 1),
            ("missing_table", "drop_order", 2),
        ):
            summary["last_operation"] = "fixture_" + action
            # The runtime-error case starts from otherwise valid customer data.
            if action == "drop_order":
                fixtures.request("load_valid")
            loaded = fixtures.request(action)
            summary["last_operation"] = "airflow_" + name
            assertion = run_case(dag, name, ready["schema"], args.target, expected_exit, loaded, output, evidence_root)
            summary["contracts"].append(assertion)
            write_json(output / "summary.json", summary)
            if not assertion["matched"]:
                raise AssertionError("Airflow integration contract mismatch")
            if name == "invalid_data":
                summary["last_operation"] = "repeat_failed_attempt"
                repeated = check_repeated_attempt(assertion, ready["schema"], args.target, output, evidence_root)
                summary["contracts"].append(repeated)
                write_json(output / "summary.json", summary)
                if not repeated["matched"]:
                    raise AssertionError("Repeated attempt replaced previous evidence")
        summary["status"] = "passed"
    except Exception as error:
        summary.update(status="failed", error_type=type(error).__name__)
    finally:
        if fixtures is not None:
            try:
                summary.update(fixtures.close())
            except Exception as error:
                summary["cleanup_error_type"] = type(error).__name__
        if not summary["cleanup_verified"] or summary.get("fixture_process_exit_code") != 0:
            summary["status"] = "failed"
        summary["finished_at_utc"] = utc_now()
        write_json(output / "summary.json", summary)
    print("Airflow quality integration {}. Evidence: {}".format(summary["status"], output), flush=True)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
