"""Run the checked-in GX 0.18 checkpoints against SQL Server, with explicit exits.

0 = all requested suites passed; 1 = data quality failure; 2 = execution/config error.
Credentials stay in memory. Output contains aggregate results, never customer rows.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

import great_expectations as gx
from great_expectations.data_context import FileDataContext
from jinja2 import Environment, StrictUndefined
from sqlalchemy.engine import URL
import yaml


CHECKPOINTS = ("customer_checkpoint", "order_checkpoint")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def load_connection(project_dir, target="dev"):
    """Reuse the selected SQL-auth dbt target without installing dbt into GX."""
    project = yaml.safe_load((project_dir / "dbt_project.yml").read_text(encoding="utf-8-sig"))
    profiles = yaml.safe_load((project_dir / "profiles.yml").read_text(encoding="utf-8-sig"))
    profile = profiles[project["profile"]]["outputs"][target]

    def env_var(name, default=None):
        if name in os.environ:
            return os.environ[name]
        if default is not None:
            return default
        raise ValueError("Missing environment variable required by selected dbt target")

    template = Environment(undefined=StrictUndefined)
    values = {
        key: template.from_string(value).render(env_var=env_var) if isinstance(value, str) else value
        for key, value in profile.items()
    }
    if values.get("type") != "sqlserver" or not values.get("user") or not values.get("password"):
        raise ValueError("The GX runner requires a SQL Server target with SQL authentication")

    def yes_no(value):
        return "yes" if str(value).lower() in ("true", "yes", "1") else "no"

    return URL.create(
        "mssql+pyodbc",
        username=values["user"],
        password=values["password"],
        host=values["server"],
        port=int(values.get("port", 1433)),
        database=values["database"],
        query={
            "driver": values.get("driver", "ODBC Driver 17 for SQL Server"),
            "Encrypt": yes_no(values.get("encrypt", True)),
            "TrustServerCertificate": yes_no(values.get("trust_cert", False)),
        },
    )


@contextmanager
def connection_environment(connection_url, schema):
    """GX interpolates escaped dollar signs; restore caller environment afterwards."""
    values = {
        "GE_CONNECTION_STRING": connection_url.render_as_string(hide_password=False).replace("$", "\\$"),
        "GE_SILVER_SCHEMA": schema,
    }
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def summarize_validation(checkpoint_name, validation, expected_rules):
    checks = []
    for item in validation.results:
        if item.exception_info and item.exception_info.get("raised_exception"):
            raise RuntimeError("An expectation raised an execution error")
        rule = item.expectation_config.meta["rule_id"]
        record = {"rule_id": rule, "success": bool(item.success)}
        # Only aggregate metrics are exported; never copy unexpected lists or queries.
        for key in ("element_count", "unexpected_count", "missing_count"):
            if key in item.result:
                record[key] = item.result[key]
        if item.expectation_config.expectation_type == "expect_table_row_count_to_be_between":
            record["observed_value"] = item.result.get("observed_value")
        checks.append(record)
    actual = [check["rule_id"] for check in checks]
    if len(actual) != len(expected_rules) or set(actual) != set(expected_rules):
        raise RuntimeError("Checkpoint did not evaluate the exact checked-in suite")
    if bool(validation.success) != all(check["success"] for check in checks):
        raise RuntimeError("Validation success disagrees with expectation results")
    return {
        "checkpoint": checkpoint_name,
        "suite": validation.meta["expectation_suite_name"],
        "success": bool(validation.success),
        "statistics": validation.statistics,
        "checks": checks,
    }


def run_checkpoints(config_dir, output_dir, connection_url, schema="silver", checkpoint_names=CHECKPOINTS):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = {
        "status": "error",
        "exit_code": 2,
        "started_at_utc": utc_now(),
        "gx_version": gx.__version__,
        "schema": schema,
        "requested_checkpoints": list(checkpoint_names),
        "validations": [],
        "configuration_sha256": {},
        "run_id": uuid.uuid4().hex,
    }
    context = None
    logging.getLogger("great_expectations").setLevel(logging.CRITICAL)
    try:
        if gx.__version__ != "0.18.22":
            raise ValueError("Use the pinned GX version from great_expectations/requirements.txt")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise ValueError("Invalid SQL schema identifier")
        if not checkpoint_names or len(set(checkpoint_names)) != len(checkpoint_names):
            raise ValueError("Select distinct nonempty checkpoints")
        if not set(checkpoint_names).issubset(CHECKPOINTS):
            raise ValueError("Unknown checkpoint")
        config_dir = Path(config_dir)
        config_files = [config_dir / "great_expectations.yml"]
        config_files += sorted((config_dir / "expectations").glob("*.json"))
        config_files += sorted((config_dir / "checkpoints").glob("*.yml"))
        summary["configuration_sha256"] = {
            str(path.relative_to(config_dir)): hashlib.sha256(path.read_bytes()).hexdigest() for path in config_files
        }
        summary["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        # Runtime store files and credentials never modify the checked-in context.
        with tempfile.TemporaryDirectory(prefix="tuan-ge-") as temporary, connection_environment(
            connection_url, schema
        ):
            runtime = Path(temporary)
            for path in config_files:
                destination = runtime / path.relative_to(config_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
            context = FileDataContext(context_root_dir=str(runtime))
            # SQL Server datetimes are interpreted as UTC; fix one bound for this run.
            validation_time = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" ")
            summary["validation_time_utc"] = validation_time
            for name in checkpoint_names:
                checkpoint = context.get_checkpoint(name)
                suite_name = checkpoint.config.validations[0]["expectation_suite_name"]
                suite = context.get_expectation_suite(suite_name)
                expected_rules = [item.meta["rule_id"] for item in suite.expectations]
                if not expected_rules or len(expected_rules) != len(set(expected_rules)):
                    raise RuntimeError("Suite requires unique nonempty rule IDs")
                result = context.run_checkpoint(
                    checkpoint_name=name,
                    run_name=summary["run_id"] + "-" + name,
                    evaluation_parameters={"validation_time": validation_time},
                )
                if len(result.run_results) != 1:
                    raise RuntimeError("Expected one validation per checkpoint")
                validation = next(iter(result.run_results.values()))["validation_result"]
                item = summarize_validation(name, validation, expected_rules)
                if result.success != item["success"] or item["suite"] != suite_name:
                    raise RuntimeError("Checkpoint result disagrees with its configured suite")
                summary["validations"].append(item)
                write_json(output_dir / (name + ".json"), item)
            passed = all(item["success"] for item in summary["validations"])
            summary.update(status="passed" if passed else "failed", exit_code=0 if passed else 1)
    except Exception as error:
        # Exception strings can include connection details or row data. Store type only.
        summary.update(status="error", exit_code=2, error_type=type(error).__name__)
        summary["error_hint"] = "Check SQL connectivity, target/schema, model existence and GX configuration."
    finally:
        if context is not None:
            try:
                context.get_datasource("adventureworks").execution_engine.close()
            except Exception as error:
                summary.update(status="error", exit_code=2, error_type=type(error).__name__)
                summary["error_hint"] = "Could not close the SQL validation connection."
        summary["finished_at_utc"] = utc_now()
        write_json(output_dir / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path("/workspace/dbt"))
    parser.add_argument("--config-dir", type=Path, default=Path("/workspace/great_expectations"))
    parser.add_argument("--target", default="dev")
    parser.add_argument("--schema", default="silver", help="Actual dbt Silver schema; explicit for other targets")
    parser.add_argument("--checkpoint", action="append", choices=CHECKPOINTS)
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="New directory; existing evidence is never replaced"
    )
    args = parser.parse_args()
    try:
        connection = load_connection(args.project_dir, args.target)
        summary = run_checkpoints(
            args.config_dir, args.output_dir, connection, args.schema, tuple(args.checkpoint or CHECKPOINTS)
        )
    except Exception as error:
        print(
            "GX could not start ({}); check profile/environment and use a new output directory.".format(
                type(error).__name__
            )
        )
        return 2
    print(
        "GX {}: {} checkpoint(s), exit {}. Evidence: {}".format(
            summary["status"], len(summary["validations"]), summary["exit_code"], args.output_dir
        )
    )
    if summary["status"] == "error":
        print("{}: {}".format(summary["error_type"], summary["error_hint"]))
    return summary["exit_code"]


if __name__ == "__main__":
    sys.exit(main())
