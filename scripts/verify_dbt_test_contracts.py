#!/usr/bin/env python3
"""Exercise the real generic tests using isolated SQL Server fixture views.

Run inside the dbt container, using installed dbt/PyYAML; no installs or network
access are needed. Example:
    python /tmp/verify_dbt_test_contracts.py --project-dir /usr/app/dbt \
        --output-dir /tmp/tuan-test-contract-evidence

The existing profile is copied privately into a temporary project and its schema
is replaced with a unique fixture schema. Only that schema's two fixture views
are created/dropped. Expected invalid rows must produce dbt test exit code 1;
this runner exits 0 only when all expected statuses/counts and cleanup succeed.
The output directory must be new or empty; it can be a mounted evidence path.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
import uuid

import yaml


GENERIC_TESTS = ("positive_values", "no_future_dates", "line_total_matches")
EXPECTED_FAILURES = {
    "valid_nonnegative": 0,
    "valid_strict_positive": 0,
    "valid_no_future_dates": 0,
    "valid_line_total": 0,
    "invalid_nonnegative": 2,
    "invalid_strict_positive": 3,
    "invalid_no_future_dates": 2,
    "invalid_line_total": 3,
}
FIXTURE_MODELS = ("contract_valid", "contract_invalid")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fixture_sql(rows):
    """Fixed literal fixtures; identifiers with spaces exercise adapter.quote."""
    columns = (
        ("case id", "int"),
        ("amount allowed", "decimal(18, 6)"),
        ("amount strict", "decimal(18, 6)"),
        ("occurred at", "datetime2(7)"),
        ("quantity", "decimal(18, 6)"),
        ("unit price", "decimal(18, 6)"),
        ("discount rate", "decimal(9, 6)"),
        ("line total", "decimal(28, 8)"),
    )
    literals = []
    for row in rows:
        literals.append(
            "    ("
            + ", ".join(
                "cast({} as {})".format("null" if value is None else value, sql_type)
                for value, (_, sql_type) in zip(row, columns)
            )
            + ")"
        )
    return (
        "select *\nfrom (values\n"
        + ",\n".join(literals)
        + "\n) as fixture ("
        + ", ".join("[{}]".format(name) for name, _ in columns)
        + ")\n"
    )


def fixture_models():
    # +/-0.01 is valid; +/-0.010001 is invalid. Decimal fractions catch float
    # arithmetic mistakes. Each missing line-total input has its own NULL case.
    valid = [
        (1, "0", "1", "dateadd(day, -1, getutcdate())", "2", "10", "0", "20"),
        (2, "0.000001", "0.000001", "getutcdate()", "3", "10", "0.1", "27.01"),
        (3, "1", "2", "dateadd(day, -2, getutcdate())", "3", "10", "0.1", "26.99"),
        (4, "3", "1", None, "2", "0.01", "0.25", "0.015"),
        (5, None, None, None, None, "10", "0", "999"),
        (6, None, None, None, "1", None, "0", "999"),
        (7, None, None, None, "1", "10", None, "999"),
        (8, None, None, None, "1", "10", "0", None),
    ]
    invalid = [
        (1, "-0.000001", "-0.000001", "dateadd(minute, 5, getutcdate())", "3", "10", "0.1", "27.010001"),
        (2, "-1", "-1", "dateadd(day, 1, getutcdate())", "3", "10", "0.1", "26.989999"),
        (3, "0", "0", "dateadd(day, -1, getutcdate())", "3", "10", "0.1", "99"),
        (4, "1", "1", "getutcdate()", "3", "10", "0.1", "27"),
        (5, None, None, None, None, "10", "0", "999"),
    ]
    return {"contract_valid": fixture_sql(valid), "contract_invalid": fixture_sql(invalid)}


def fixture_schema_yaml():
    models = []
    for label in ("valid", "invalid"):
        models.append(
            {
                "name": "contract_" + label,
                "columns": [
                    {
                        "name": "amount allowed",
                        "data_tests": [
                            {
                                "positive_values": {
                                    "name": label + "_nonnegative",
                                }
                            }
                        ],
                    },
                    {
                        "name": "amount strict",
                        "data_tests": [
                            {
                                "positive_values": {
                                    "name": label + "_strict_positive",
                                    "allow_zero": False,
                                }
                            }
                        ],
                    },
                    {
                        "name": "occurred at",
                        "data_tests": [
                            {
                                "no_future_dates": {
                                    "name": label + "_no_future_dates",
                                }
                            }
                        ],
                    },
                ],
                "data_tests": [
                    {
                        "line_total_matches": {
                            "name": label + "_line_total",
                            "quantity_column": "quantity",
                            "unit_price_column": "unit price",
                            "discount_column": "discount rate",
                            "line_total_column": "line total",
                        }
                    }
                ],
            }
        )
    return {"version": 2, "models": models}


LIFECYCLE_MACROS = r"""
{% macro assert_contract_schema() %}
    {% if target.schema != var('contract_schema') or not target.schema.startswith('tuan_test_contracts_') %}
        {{ exceptions.raise_compiler_error('Refusing to touch a non-fixture schema') }}
    {% endif %}
{% endmacro %}

{% macro claim_contract_schema() %}
    {% do assert_contract_schema() %}
    {% set existing = run_query("select name from sys.schemas where name = '" ~ target.schema ~ "'") %}
    {% if existing.rows | length != 0 %}
        {{ exceptions.raise_compiler_error('Fixture schema already exists; refusing to use it') }}
    {% endif %}
    {% do run_query('create schema ' ~ adapter.quote(target.schema)) %}
    {% do run_query('if @@trancount > 0 commit transaction') %}
{% endmacro %}

{% macro cleanup_contract_schema() %}
    {% do assert_contract_schema() %}
    {% for model_name in ['contract_valid', 'contract_invalid'] %}
        {% set relation = adapter.get_relation(database=target.database, schema=target.schema, identifier=model_name) %}
        {% if relation is not none %}
            {% do adapter.drop_relation(relation) %}
        {% endif %}
    {% endfor %}
    {# DROP SCHEMA fails if an unexpected object remains; never drop other objects. #}
    {% do run_query('drop schema ' ~ adapter.quote(target.schema)) %}
    {% do run_query('if @@trancount > 0 commit transaction') %}
{% endmacro %}

{% macro verify_contract_schema_absent() %}
    {% do assert_contract_schema() %}
    {% set remaining = run_query("select name from sys.schemas where name = '" ~ target.schema ~ "'") %}
    {% if remaining.rows | length != 0 %}
        {{ exceptions.raise_compiler_error('Fixture schema still exists after cleanup') }}
    {% endif %}
{% endmacro %}
"""


def run_dbt(project, output_dir, summary, label, command, env):
    args = ["dbt"] + command + ["--project-dir", str(project), "--profiles-dir", str(project)]
    step = {"command": "dbt " + " ".join(command), "started_at_utc": utc_now()}
    summary["steps"][label] = step
    write_json(output_dir / "summary.json", summary)
    result = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env
    )
    (output_dir / (label + ".stdout.txt")).write_text(result.stdout, encoding="utf-8")
    step.update(exit_code=result.returncode, finished_at_utc=utc_now(), stdout_file=label + ".stdout.txt")
    write_json(output_dir / "summary.json", summary)
    print("{}: exit {}".format(label, result.returncode), flush=True)
    return result.returncode


def snapshot_results(project, output_dir, command):
    source = project / "target" / "run_results.json"
    artifact = json.loads(source.read_text(encoding="utf-8"))
    if artifact.get("args", {}).get("which") != command:
        raise RuntimeError("run_results command does not match " + command)
    shutil.copyfile(source, output_dir / (command + ".run_results.json"))
    return artifact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path("/usr/app/dbt"))
    parser.add_argument("--profiles-dir", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_project = args.project_dir.resolve()
    profiles_dir = (args.profiles_dir or source_project).resolve()
    output_dir = args.output_dir.resolve()
    if output_dir.exists() and any(output_dir.iterdir()):
        parser.error("--output-dir must be new or empty; existing evidence is preserved")
    output_dir.mkdir(parents=True, exist_ok=True)
    if shutil.which("dbt") is None:
        parser.error("dbt is not installed; run this script inside the existing dbt container")

    schema_name = "tuan_test_contracts_" + uuid.uuid4().hex
    summary = {
        "started_at_utc": utc_now(),
        "finished_at_utc": None,
        "status": "running",
        "fixture_schema": schema_name,
        "steps": {},
        "generic_test_sha256": {},
        "expected_test_exit_code": 1,
        "contracts": [],
        "contracts_verified": False,
        "cleanup_verified": False,
    }
    write_json(output_dir / "summary.json", summary)
    with tempfile.TemporaryDirectory(prefix="tuan-dbt-test-contracts-") as temporary:
        project = Path(temporary)
        claimed = False
        env = os.environ.copy()
        env.update(
            DBT_USE_COLORS="false",
            DBT_TARGET_PATH=str(project / "target"),
            DBT_LOG_PATH=str(project / "logs"),
            DBT_SEND_ANONYMOUS_USAGE_STATS="false",
        )
        try:
            source_config = yaml.safe_load((source_project / "dbt_project.yml").read_text(encoding="utf-8"))
            profile_name = source_config["profile"]
            profiles = yaml.safe_load((profiles_dir / "profiles.yml").read_text(encoding="utf-8"))
            existing_profile = profiles[profile_name]
            target_name = args.target or existing_profile["target"]
            target_profile = dict(existing_profile["outputs"][target_name])
            target_profile.update(schema=schema_name, threads=1)
            (project / "profiles.yml").write_text(
                yaml.safe_dump(
                    {
                        profile_name: {
                            "target": target_name,
                            "outputs": {target_name: target_profile},
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (project / "profiles.yml").chmod(0o600)
            (project / "dbt_project.yml").write_text(
                yaml.safe_dump(
                    {
                        "name": "tuan_test_contracts",
                        "version": "1.0.0",
                        "config-version": 2,
                        "profile": profile_name,
                        "model-paths": ["models"],
                        "test-paths": ["tests"],
                        "macro-paths": ["macros"],
                        "target-path": "target",
                        "vars": {"contract_schema": schema_name},
                        "models": {"tuan_test_contracts": {"+materialized": "view"}},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (project / "tests" / "generic").mkdir(parents=True)
            (project / "models").mkdir()
            (project / "macros").mkdir()
            for test_name in GENERIC_TESTS:
                source = source_project / "tests" / "generic" / (test_name + ".sql")
                summary["generic_test_sha256"][test_name] = hashlib.sha256(source.read_bytes()).hexdigest()
                shutil.copyfile(source, project / "tests" / "generic" / source.name)
            for model_name, sql in fixture_models().items():
                (project / "models" / (model_name + ".sql")).write_text(sql, encoding="utf-8")
                (output_dir / (model_name + ".sql")).write_text(sql, encoding="utf-8")
            (project / "models" / "schema.yml").write_text(
                yaml.safe_dump(fixture_schema_yaml(), sort_keys=False), encoding="utf-8"
            )
            (project / "macros" / "lifecycle.sql").write_text(LIFECYCLE_MACROS, encoding="utf-8")

            claim_exit = run_dbt(
                project, output_dir, summary, "claim_schema", ["run-operation", "claim_contract_schema"], env
            )
            if claim_exit != 0:
                raise RuntimeError("Could not claim an isolated fixture schema; see claim_schema.stdout.txt")
            claimed = True
            run_exit = run_dbt(project, output_dir, summary, "run", ["run"], env)
            if run_exit != 0:
                raise RuntimeError("Fixture models failed to build; see run.stdout.txt")
            model_results = snapshot_results(project, output_dir, "run")["results"]
            if len(model_results) != 2 or any(item["status"] != "success" for item in model_results):
                raise RuntimeError("Expected two successful fixture models")

            test_exit = run_dbt(project, output_dir, summary, "test", ["test"], env)
            test_results = snapshot_results(project, output_dir, "test")["results"]
            actual = {item["unique_id"].split(".")[2]: item for item in test_results}
            if len(test_results) != len(EXPECTED_FAILURES) or set(actual) != set(EXPECTED_FAILURES):
                raise RuntimeError("Expected exactly the eight named fixture tests")
            for name, expected_count in EXPECTED_FAILURES.items():
                item = actual[name]
                expected_status = "pass" if expected_count == 0 else "fail"
                summary["contracts"].append(
                    {
                        "name": name,
                        "expected_status": expected_status,
                        "actual_status": item["status"],
                        "expected_failures": expected_count,
                        "actual_failures": item.get("failures"),
                        "matched": item["status"] == expected_status and item.get("failures") == expected_count,
                    }
                )
            if test_exit != 1 or not all(item["matched"] for item in summary["contracts"]):
                raise RuntimeError("Generic-test contracts did not match expected statuses/counts and exit code 1")
            summary["contracts_verified"] = True
        except Exception as error:
            summary["status"] = "failed"
            summary["error"] = str(error)
        finally:
            if claimed:
                try:
                    cleanup_exit = run_dbt(
                        project, output_dir, summary, "cleanup", ["run-operation", "cleanup_contract_schema"], env
                    )
                    if cleanup_exit != 0:
                        summary["status"] = "failed"
                        summary["cleanup_error"] = "Fixture schema cleanup failed; see cleanup.stdout.txt"
                    else:
                        # A fresh connection proves cleanup was committed, not
                        # merely visible inside the cleanup transaction.
                        verify_exit = run_dbt(
                            project,
                            output_dir,
                            summary,
                            "verify_cleanup",
                            ["run-operation", "verify_contract_schema_absent"],
                            env,
                        )
                        summary["cleanup_verified"] = verify_exit == 0
                        if verify_exit != 0:
                            summary["status"] = "failed"
                            summary["cleanup_error"] = "Fixture schema remains; see verify_cleanup.stdout.txt"
                except Exception as error:
                    summary["status"] = "failed"
                    summary["cleanup_error"] = str(error)
            if summary["contracts_verified"] and summary["cleanup_verified"] and summary["status"] != "failed":
                summary["status"] = "passed"
            summary["finished_at_utc"] = utc_now()
            write_json(output_dir / "summary.json", summary)
    print("Contract verification {}. Evidence: {}".format(summary["status"], output_dir), flush=True)
    return 0 if summary["status"] == "passed" and summary["cleanup_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
