"""Report dbt test inventory and execution coverage without claiming semantic coverage."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

SOURCE_CALL = re.compile(r"source\(\s*(['\"])([^'\"]+)\1\s*,\s*(['\"])([^'\"]+)\3\s*\)")
REF_CALL = re.compile(r"ref\(\s*(['\"][^'\"]+['\"](?:\s*,\s*['\"][^'\"]+['\"])?)(?:\s*)\)")


def unique_object(pairs):
    """Reject duplicate JSON keys instead of silently losing inventory entries."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key")
        result[key] = value
    return result


def load_artifact(path):
    content = path.read_bytes()
    value = json.loads(content.decode("utf-8-sig"), object_pairs_hook=unique_object)
    if not isinstance(value, dict):
        raise ValueError("Artifact root must be an object")
    return value, {"path": path.as_posix(), "sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def enabled(node):
    return node.get("config", {}).get("enabled", True) is not False


def result_inventory(artifact):
    results = artifact.get("results")
    if not isinstance(results, list) or not all(isinstance(row, dict) for row in results):
        raise ValueError("run_results.results must be an array of objects")
    ids = [row.get("unique_id") for row in results]
    if not all(isinstance(item, str) and item.startswith("test.") for item in ids):
        raise ValueError("run_results must contain test nodes with unique IDs")
    return results, Counter(ids)


def generic_target(test, resources):
    """Resolve the tested relation, excluding a relationships test's parent relation."""
    attached = test.get("attached_node")
    if attached:
        return attached if attached in resources else None
    expression = test["test_metadata"].get("kwargs", {}).get("model", "")
    if not isinstance(expression, str):
        return None
    match = SOURCE_CALL.search(expression)
    if match:
        candidates = [
            uid
            for uid, node in resources.items()
            if node.get("resource_type") == "source"
            and (node.get("source_name"), node.get("name")) == (match.group(2), match.group(4))
        ]
    else:
        match = REF_CALL.search(expression)
        if not match:
            return None
        names = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
        candidates = [
            uid
            for uid, node in resources.items()
            if node.get("resource_type") == "model"
            and node.get("name") == names[-1]
            and (len(names) == 1 or node.get("package_name") == names[0])
        ]
    dependencies = test.get("depends_on", {}).get("nodes", [])
    candidates = [uid for uid in candidates if uid in dependencies]
    return candidates[0] if len(candidates) == 1 else None


def active_source_ids(models, nodes, sources):
    visited = set()
    pending = list(models)
    while pending:
        uid = pending.pop()
        if uid in visited:
            continue
        visited.add(uid)
        node = nodes.get(uid)
        if node:
            pending.extend(node.get("depends_on", {}).get("nodes", []))
    return visited.intersection(sources)


def resource_report(uid, node, tests, active=None):
    columns = node.get("columns", {})
    documented = {name for name, value in columns.items() if str(value.get("description") or "").strip()}
    by_column = defaultdict(list)
    for test in tests:
        if test["column_name"]:
            by_column[test["column_name"].casefold()].append(test["unique_id"])
    directly_tested = sorted(name for name in columns if name.casefold() in by_column)
    result = {
        "unique_id": uid,
        "name": node["name"],
        "resource_type": node["resource_type"],
        "declared_column_count": len(columns),
        "documented_column_count": len(documented),
        "generic_test_count": len(tests),
        "generic_test_ids": sorted(test["unique_id"] for test in tests),
        "generic_table_test_ids": sorted(test["unique_id"] for test in tests if not test["column_name"]),
        "directly_tested_declared_column_count": len(directly_tested),
        "directly_tested_documented_column_count": len(set(directly_tested).intersection(documented)),
        "directly_tested_columns": directly_tested,
        "columns_without_direct_generic_tests": sorted(name for name in columns if name.casefold() not in by_column),
        "column_test_ids": {name: sorted(by_column[name.casefold()]) for name in directly_tested},
        "tested_columns_not_declared": sorted(set(by_column) - {name.casefold() for name in columns}),
    }
    if active is not None:
        result.update(source_name=node["source_name"], used_by_model_ancestry=active)
    return result


def build_report(manifest, run_results, baseline, artifacts):
    nodes = manifest.get("nodes")
    sources = manifest.get("sources")
    if not isinstance(nodes, dict) or not isinstance(sources, dict):
        raise ValueError("Manifest must contain nodes and sources objects")
    models = {uid: node for uid, node in nodes.items() if node.get("resource_type") == "model" and enabled(node)}
    sources = {uid: node for uid, node in sources.items() if enabled(node)}
    tests = {uid: node for uid, node in nodes.items() if node.get("resource_type") == "test" and enabled(node)}
    resources = {**models, **sources}
    rows, result_counts = result_inventory(run_results)
    baseline_rows, baseline_counts = result_inventory(baseline)
    if any(count > 1 for count in baseline_counts.values()):
        raise ValueError("Baseline result IDs must be unique")
    problems = []
    if not tests:
        problems.append({"code": "empty_test_inventory"})
    for uid, node in {**nodes, **sources}.items():
        if node.get("unique_id") != uid:
            problems.append({"code": "manifest_node_id_mismatch", "key": uid})
    missing = sorted(set(tests) - set(result_counts))
    extra = sorted(set(result_counts) - set(tests))
    duplicates = sorted(uid for uid, count in result_counts.items() if count > 1)
    for code, ids in (
        ("missing_result_ids", missing),
        ("extra_result_ids", extra),
        ("duplicate_result_ids", duplicates),
    ):
        if ids:
            problems.append({"code": code, "unique_ids": ids})
    nonpassing = [
        {"unique_id": row["unique_id"], "status": row.get("status"), "failures": row.get("failures")}
        for row in rows
        if row.get("status") != "pass"
    ]
    if nonpassing:
        problems.append({"code": "nonpassing_results", "results": nonpassing})
    manifest_invocation = manifest.get("metadata", {}).get("invocation_id")
    results_invocation = run_results.get("metadata", {}).get("invocation_id")
    if not manifest_invocation or not results_invocation or manifest_invocation != results_invocation:
        problems.append({"code": "manifest_results_invocation_mismatch"})
    inventory = []
    by_target = defaultdict(list)
    categories = Counter()
    for uid, test in sorted(tests.items()):
        metadata = test.get("test_metadata")
        item = {"unique_id": uid, "name": test["name"], "dependencies": test.get("depends_on", {}).get("nodes", [])}
        if metadata:
            target = generic_target(test, resources)
            column = test.get("column_name") or metadata.get("kwargs", {}).get("column_name")
            if column is not None and not isinstance(column, str):
                raise ValueError("Test column_name must be a string or null")
            item.update(
                kind="generic",
                test_type=metadata["name"],
                namespace=metadata.get("namespace"),
                target_unique_id=target,
                column_name=column,
            )
            categories[metadata["name"]] += 1
            if target is None or target not in item["dependencies"]:
                problems.append({"code": "generic_target_unresolved", "unique_id": uid})
            else:
                by_target[target].append(item)
        else:
            item.update(kind="singular", test_type=None, target_unique_id=None, column_name=None)
            categories["singular"] += 1
        inventory.append(item)
    active = active_source_ids(models, nodes, sources)
    model_reports = [resource_report(uid, node, by_target[uid]) for uid, node in sorted(models.items())]
    source_reports = [
        resource_report(uid, node, by_target[uid], uid in active) for uid, node in sorted(sources.items())
    ]
    kinds = Counter(item["kind"] for item in inventory)
    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "failed" if problems else "passed",
        "problems": problems,
        "artifacts": artifacts,
        "invocation": {"manifest": manifest_invocation, "run_results": results_invocation},
        "execution": {
            "enabled_test_nodes": len(tests),
            "result_rows": len(rows),
            "unique_result_nodes": len(result_counts),
            "status_counts": dict(sorted(Counter(str(row.get("status")) for row in rows).items())),
            "missing_result_ids": missing,
            "extra_result_ids": extra,
            "duplicate_result_ids": duplicates,
            "exact_enabled_test_set_executed": not (missing or extra or duplicates),
        },
        "inventory": {
            "generic_test_nodes": kinds["generic"],
            "singular_test_nodes": kinds["singular"],
            "test_type_counts": dict(sorted(categories.items())),
            "model_nodes": len(models),
            "models_with_direct_generic_tests": sum(bool(item["generic_test_count"]) for item in model_reports),
            "model_declared_columns": sum(item["declared_column_count"] for item in model_reports),
            "model_documented_columns": sum(item["documented_column_count"] for item in model_reports),
            "model_columns_with_direct_generic_tests": sum(
                item["directly_tested_declared_column_count"] for item in model_reports
            ),
            "active_source_nodes": len(active),
            "unused_source_nodes": len(sources) - len(active),
            "active_source_declared_columns": sum(
                item["declared_column_count"] for item in source_reports if item["used_by_model_ancestry"]
            ),
        },
        "baseline_comparison": {
            "baseline_unique_test_nodes": len(baseline_counts),
            "baseline_status_counts": dict(sorted(Counter(str(row.get("status")) for row in baseline_rows).items())),
            "added_test_ids": sorted(set(tests) - set(baseline_counts)),
            "removed_test_ids": sorted(set(baseline_counts) - set(tests)),
        },
        "models": model_reports,
        "sources": source_reports,
        "tests": inventory,
        "limitations": [
            "A passed report proves inventory/result consistency and passing configured tests, "
            "not complete data quality.",
            "Direct column coverage counts only column-level generic tests attached to that tested relation.",
            "Relationships targets are distinguished from referenced parents; "
            "dependencies alone do not prove coverage.",
            "Table-level and singular tests can cover more columns; their semantic coverage is not inferred from SQL.",
            "No direct generic test can be intentional for nullable/descriptive fields "
            "or fields covered by GE/singular tests.",
            "Declared source columns may be a subset of the physical source schema.",
            "Baseline IDs detect additions/removals, not changes to existing SQL or generic test semantics.",
            "GE expectations and source freshness are separate validations "
            "and are not counted as dbt test coverage.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--run-results", required=True, type=Path)
    parser.add_argument("--baseline-results", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; select a new path")
    try:
        manifest, manifest_artifact = load_artifact(args.manifest)
        results, results_artifact = load_artifact(args.run_results)
        baseline, baseline_artifact = load_artifact(args.baseline_results)
        report = build_report(
            manifest,
            results,
            baseline,
            {"manifest": manifest_artifact, "run_results": results_artifact, "baseline_results": baseline_artifact},
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(json.dumps({"status": "error", "error_type": type(exc).__name__}))
        return 2
    print(
        json.dumps(
            {
                "status": report["status"],
                "enabled_test_nodes": report["execution"]["enabled_test_nodes"],
                "result_rows": report["execution"]["result_rows"],
                "problem_count": len(report["problems"]),
                "output": args.output.as_posix(),
            }
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
