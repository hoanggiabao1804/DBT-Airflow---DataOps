"""Exercise real source freshness and timestamp tests on isolated SQL Server views.

Run inside the dbt container. Copy verify_dbt_test_contracts.py alongside this
file: its logging helpers are reused. No source tables or dbt models are changed.
The runner succeeds only when expected pass/warn/error cases, test failure
counts, exit codes and fixture-schema cleanup all match.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import uuid

from jinja2 import Environment, StrictUndefined
import yaml

from verify_dbt_test_contracts import run_dbt, utc_now, write_json


FRESHNESS_EXPECTED = {
    "fresh": "pass",
    "warning": "warn",
    "stale": "error",
    "missing": "error",
    "future": "pass",
    "mixed_null": "pass",
    "empty": "error",
}
TEST_FAILURES = {"missing_not_null": 1, "future_no_future_dates": 1, "mixed_null_not_null": 1}
LIFECYCLE = r"""
{% macro check_fixture_schema() %}
    {% if target.schema != var('fixture_schema') or not target.schema.startswith('tuan_freshness_contracts_') %}
        {{ exceptions.raise_compiler_error('Refusing to touch a non-fixture schema') }}
    {% endif %}
{% endmacro %}
{% macro claim_fixture_schema() %}
    {% do check_fixture_schema() %}
    {% set existing = run_query("select name from sys.schemas where name = '" ~ target.schema ~ "'") %}
    {% if existing.rows | length != 0 %}
        {{ exceptions.raise_compiler_error('Fixture schema already exists') }}
    {% endif %}
    {% do run_query('create schema ' ~ adapter.quote(target.schema)) %}
    {% do run_query('if @@trancount > 0 commit transaction') %}
{% endmacro %}
{% macro cleanup_fixture_schema() %}
    {% do check_fixture_schema() %}
    {% for name in var('fixture_names') %}
        {% set relation = adapter.get_relation(database=target.database, schema=target.schema, identifier=name) %}
        {% if relation is not none %}{% do adapter.drop_relation(relation) %}{% endif %}
    {% endfor %}
    {# Fail if any unexpected object remains; never drop unrelated objects. #}
    {% do run_query('drop schema ' ~ adapter.quote(target.schema)) %}
    {% do run_query('if @@trancount > 0 commit transaction') %}
{% endmacro %}
{% macro verify_fixture_absent() %}
    {% do check_fixture_schema() %}
    {% set remaining = run_query("select name from sys.schemas where name = '" ~ target.schema ~ "'") %}
    {% if remaining.rows | length != 0 %}
        {{ exceptions.raise_compiler_error('Fixture schema still exists') }}
    {% endif %}
{% endmacro %}
"""


def configure_project(source, profiles, target, project, schema, output, summary):
    """Read the checked-in source policy, not a second hard-coded threshold copy."""
    source_path = source / "models/bronze/src_adventureworks.yml"
    raw = source_path.read_bytes()
    summary["source_definition_sha256"] = hashlib.sha256(raw).hexdigest()
    template = Environment(undefined=StrictUndefined).from_string(raw.decode("utf-8-sig"))
    definitions = yaml.safe_load(template.render(var=lambda name, default: default))["sources"]
    policies = []
    for definition in definitions:
        for table in definition["tables"]:
            policies.append(
                {
                    "loaded_at_field": table.get("loaded_at_field", definition["loaded_at_field"]),
                    "freshness": table.get("freshness", definition["freshness"]),
                }
            )
    if len(policies) != 6 or any(p != policies[0] for p in policies):
        raise ValueError(
            "Expected a shared freshness policy for the six used sources; update fixture coverage if changed"
        )
    policy = policies[0]
    for level in ("warn_after", "error_after"):
        policy["freshness"][level]["count"] = int(policy["freshness"][level]["count"])
    if policy != {
        "loaded_at_field": "[ModifiedDate]",
        "freshness": {
            "warn_after": {"count": 24, "period": "hour"},
            "error_after": {"count": 48, "period": "hour"},
        },
    }:
        raise ValueError("Fixture ages exercise the default 24h/48h policy; review cases before changing the SLA")
    summary["policy"] = policy

    project_config = yaml.safe_load((source / "dbt_project.yml").read_text())
    profile_name = project_config["profile"]
    profile = yaml.safe_load((profiles / "profiles.yml").read_text())[profile_name]
    target_name = target or profile["target"]
    connection = dict(profile["outputs"][target_name])
    connection.update(schema=schema, threads=1)
    (project / "profiles.yml").write_text(
        yaml.safe_dump(
            {
                profile_name: {
                    "target": target_name,
                    "outputs": {target_name: connection},
                }
            }
        ),
        encoding="utf-8",
    )
    (project / "profiles.yml").chmod(0o600)
    (project / "dbt_project.yml").write_text(
        yaml.safe_dump(
            {
                "name": "tuan_freshness_contracts",
                "version": "1.0.0",
                "config-version": 2,
                "profile": profile_name,
                "model-paths": ["models"],
                "test-paths": ["tests"],
                "macro-paths": ["macros"],
                "vars": {"fixture_schema": schema, "fixture_names": list(FRESHNESS_EXPECTED)},
                "models": {"tuan_freshness_contracts": {"+materialized": "view"}},
            }
        ),
        encoding="utf-8",
    )
    for relative in ("models", "tests/generic", "macros"):
        (project / relative).mkdir(parents=True, exist_ok=True)
    summary["sql_sha256"] = {}
    for relative in ("tests/generic/no_future_dates.sql", "macros/sqlserver__collect_freshness.sql"):
        file = source / relative
        summary["sql_sha256"][relative] = hashlib.sha256(file.read_bytes()).hexdigest()
        shutil.copyfile(file, project / relative)
    (project / "macros/lifecycle.sql").write_text(LIFECYCLE, encoding="utf-8")
    values = {
        "fresh": "dateadd(hour, -1, sysutcdatetime())",
        "warning": "dateadd(hour, -36, sysutcdatetime())",
        "stale": "dateadd(hour, -72, sysutcdatetime())",
        "missing": "cast(null as datetime2(6))",
        "future": "dateadd(hour, 24, sysutcdatetime())",
        "mixed_null": "dateadd(hour, -1, sysutcdatetime())",
        "empty": "cast(null as datetime2(6))",
    }
    tables = []
    for name, value in values.items():
        sql = "select " + value + " as ModifiedDate"
        if name == "mixed_null":
            sql += " union all select cast(null as datetime2(6))"
        if name == "empty":
            sql += " where 1 = 0"
        (project / ("models/" + name + ".sql")).write_text(sql + "\n", encoding="utf-8")
        (output / (name + ".sql")).write_text(sql + "\n", encoding="utf-8")
        tables.append(
            {
                "name": name,
                "columns": [
                    {
                        "name": "ModifiedDate",
                        "data_tests": [{test: {"name": name + "_" + test}} for test in ("not_null", "no_future_dates")],
                    }
                ],
            }
        )
    source_yaml = {
        "version": 2,
        "sources": [
            {
                "name": "fixture",
                "schema": schema,
                **policy,
                "tables": tables,
            }
        ],
    }
    (project / "models/sources.yml").write_text(yaml.safe_dump(source_yaml), encoding="utf-8")
    write_json(output / "policy.json", policy)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path("/usr/app/dbt"))
    parser.add_argument("--profiles-dir", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory must be new or empty; existing evidence is preserved")
    output.mkdir(parents=True, exist_ok=True)
    schema = "tuan_freshness_contracts_" + uuid.uuid4().hex
    summary = {
        "started_at_utc": utc_now(),
        "status": "running",
        "steps": {},
        "fixture_schema": schema,
        "contracts": [],
        "cleanup_verified": False,
    }
    write_json(output / "summary.json", summary)
    with tempfile.TemporaryDirectory(prefix="tuan-freshness-") as temporary:
        project = Path(temporary)
        claimed = False
        env = os.environ.copy()
        env.update(DBT_USE_COLORS="false", DBT_SEND_ANONYMOUS_USAGE_STATS="false")

        def run(label, command, artifact=None):
            # Distinct target paths prevent an old artifact from proving a new step.
            env.update(DBT_TARGET_PATH=str(project / "artifacts" / label), DBT_LOG_PATH=str(project / "logs" / label))
            code = run_dbt(project, output, summary, label, command, env)
            if artifact is None:
                return code, None
            file = Path(env["DBT_TARGET_PATH"]) / artifact
            data = json.loads(file.read_text(encoding="utf-8"))
            shutil.copyfile(file, output / (label + "." + artifact))
            return code, data

        try:
            configure_project(
                args.project_dir, args.profiles_dir or args.project_dir, args.target, project, schema, output, summary
            )
            code, _ = run("claim_schema", ["run-operation", "claim_fixture_schema"])
            if code != 0:
                raise RuntimeError("Could not claim a private fixture schema")
            claimed = True
            code, built = run("run", ["run"], "run_results.json")
            if code != 0 or len(built["results"]) != 7 or any(r["status"] != "success" for r in built["results"]):
                raise RuntimeError("Expected seven fixture views to build")
            for label, selection, expected, exit_code in (
                ("fresh_only", "source:fixture.fresh", {"fresh": "pass"}, 0),
                ("warn_only", "source:fixture.warning", {"warning": "warn"}, 0),
                ("all_sources", "source:fixture", FRESHNESS_EXPECTED, 1),
            ):
                code, artifact = run(label, ["source", "freshness", "--select", selection], "sources.json")
                actual = {r["unique_id"].split(".")[-1]: r["status"] for r in artifact["results"]}
                matched = code == exit_code and actual == expected and len(artifact["results"]) == len(expected)
                summary["contracts"].append(
                    {
                        "case": label,
                        "expected": expected,
                        "actual": actual,
                        "expected_exit_code": exit_code,
                        "actual_exit_code": code,
                        "matched": matched,
                    }
                )
                if not matched:
                    raise RuntimeError("Freshness contract mismatch: " + label)
            code, tests = run("timestamp_tests", ["test"], "run_results.json")
            expected_names = {
                name + "_" + test for name in FRESHNESS_EXPECTED for test in ("not_null", "no_future_dates")
            }
            actual = {item["unique_id"].split(".")[2]: item for item in tests["results"]}
            if code != 1 or len(tests["results"]) != 14 or set(actual) != expected_names:
                raise RuntimeError("Expected fourteen named timestamp tests, with exit 1 for invalid fixtures")
            for name, item in sorted(actual.items()):
                failures = TEST_FAILURES.get(name, 0)
                expected_status = "fail" if failures else "pass"
                matched = item["status"] == expected_status and item.get("failures") == failures
                summary["contracts"].append(
                    {
                        "case": name,
                        "expected_status": expected_status,
                        "actual_status": item["status"],
                        "expected_failures": failures,
                        "actual_failures": item.get("failures"),
                        "matched": matched,
                    }
                )
            if not all(item["matched"] for item in summary["contracts"]):
                raise RuntimeError("Timestamp test contracts did not match")
            summary["status"] = "passed"
        except Exception as error:
            summary.update(status="failed", error=str(error))
        finally:
            if claimed:
                try:
                    cleanup, _ = run("cleanup", ["run-operation", "cleanup_fixture_schema"])
                    if cleanup == 0:
                        verified, _ = run("verify_cleanup", ["run-operation", "verify_fixture_absent"])
                        summary["cleanup_verified"] = verified == 0
                except Exception as error:
                    summary["cleanup_error"] = str(error)
            if not summary["cleanup_verified"]:
                summary["status"] = "failed"
            summary["finished_at_utc"] = utc_now()
            write_json(output / "summary.json", summary)
    print("Freshness contracts {}. Evidence: {}".format(summary["status"], output), flush=True)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
