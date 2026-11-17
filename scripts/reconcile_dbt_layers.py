"""Capture read-only Bronze/Silver/Gold reconciliation against a fresh dbt test run.

Run in ge-worker, whose mounted dbt profile supplies connection credentials.
The queries share one SERIALIZABLE transaction after dbt has finished; no source
or model data is changed. Reports contain aggregate numbers, never customer rows.
Exit 0 means reconciled, 1 means a mismatch, 2 means invalid inputs/runtime error.
"""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from sqlalchemy import create_engine, text

from run_ge_checkpoints import load_connection

MODELS = (
    "brnz_customers",
    "brnz_products",
    "brnz_sales_orders",
    "brnz_example",
    "slvr_customers",
    "slvr_products",
    "slvr_sales_orders",
    "gld_customer_metrics",
    "gld_product_performance",
    "gld_sales_summary",
)
RECONCILIATIONS = {
    "assert_silver_customer_preservation",
    "assert_silver_product_preservation",
    "assert_silver_eligible_order_lines",
    "assert_customer_metrics_reconciliation",
    "assert_product_metrics_reconciliation",
    "assert_daily_sales_reconciliation",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def relation(node):
    parts = (node["database"], node["schema"], node.get("alias") or node.get("identifier"))
    if not all(isinstance(part, str) and part for part in parts):
        raise ValueError("Incomplete relation metadata")
    return ".".join("[" + part.replace("]", "]]") + "]" for part in parts)


def scalar(connection, sql):
    return connection.execute(text(sql)).scalar_one()


def sales_metrics(connection, table, predicate="1 = 1"):
    sql = """select count_big(*) as lines, count(distinct sales_order_id) as orders,
        sum(cast(order_qty as bigint)) as quantity,
        sum(cast(line_total as decimal(38,6))) as net_revenue,
        min(order_date) as first_order_date, max(order_date) as last_order_date
        from {} where {}""".format(table, predicate)
    return dict(connection.execute(text(sql)).mappings().one())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--run-results", type=Path, required=True)
    parser.add_argument("--project-dir", type=Path, default=Path("/workspace/dbt"))
    parser.add_argument("--target", default="dev")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    report = {"status": "error", "exit_code": 2, "started_at_utc": now(), "checks": []}
    engine = None
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        results = json.loads(args.run_results.read_text(encoding="utf-8-sig"))
        if results["args"]["which"] != "test" or results["args"]["target"] != args.target:
            raise ValueError("A dbt test result for the selected target is required")
        if manifest["metadata"]["invocation_id"] != results["metadata"]["invocation_id"]:
            raise ValueError("Manifest and test results must belong to the same invocation")
        if not results["results"] or any(item["status"] != "pass" for item in results["results"]):
            raise ValueError("The complete dbt test run must pass before reconciliation")
        nodes = manifest["nodes"]
        models = {node["name"]: node for node in nodes.values() if node["resource_type"] == "model"}
        if set(models) != set(MODELS):
            raise ValueError("Unexpected model inventory")
        tests = {node["name"]: node for node in nodes.values() if node["name"] in RECONCILIATIONS}
        if set(tests) != RECONCILIATIONS:
            raise ValueError("Missing reconciliation tests")
        result_ids = {item["unique_id"] for item in results["results"]}
        manifest_test_ids = {
            node_id
            for node_id, node in nodes.items()
            if node["resource_type"] == "test" and node.get("config", {}).get("enabled", True)
        }
        if result_ids != manifest_test_ids or len(result_ids) != len(results["results"]):
            raise ValueError("Test results must cover every enabled manifest test exactly once")
        if not all(node["unique_id"] in result_ids for node in tests.values()):
            raise ValueError("Reconciliation tests were not executed")
        code_hashes = {}
        for node in list(models.values()) + list(tests.values()):
            path = args.project_dir / node["original_file_path"]
            raw = path.read_text(encoding="utf-8-sig")
            if raw.replace("\r\n", "\n").strip() != node["raw_code"].replace("\r\n", "\n").strip():
                raise ValueError("Runtime artifact does not match current project SQL")
            code_hashes[node["original_file_path"]] = sha(path)
        active_sources = set()
        pending = [node["unique_id"] for node in models.values()]
        visited = set()
        while pending:
            node_id = pending.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            if node_id in manifest["sources"]:
                active_sources.add(node_id)
            elif node_id in nodes:
                pending.extend(nodes[node_id]["depends_on"]["nodes"])
        tables = {name: relation(node) for name, node in models.items()}
        report.update(
            target=args.target,
            dbt_test_invocation_id=results["metadata"]["invocation_id"],
            dbt_test_count=len(results["results"]),
            input_sha256={"manifest": sha(args.manifest), "run_results": sha(args.run_results)},
            sql_sha256=code_hashes,
            runner_sha256=sha(Path(__file__)),
            consistency=(
                "Read-only queries in one SERIALIZABLE transaction after dbt; "
                "not a snapshot shared with the earlier dbt run."
            ),
            freshness="Not executed; historical-source issue DQ-W2-01 remains open.",
            monetary_tolerance="0.01",
        )
        engine = create_engine(load_connection(args.project_dir, args.target), pool_pre_ping=True)
        with engine.connect().execution_options(isolation_level="SERIALIZABLE") as connection:
            with connection.begin():
                database = scalar(connection, "select db_name()")
                if any(node["database"] != database for node in models.values()):
                    raise ValueError("Target database and manifest disagree")
                report["database"] = database
                report["snapshot_started_at_utc"] = now()
                report["model_rows"] = {
                    name: scalar(connection, "select count_big(*) from " + table) for name, table in tables.items()
                }
                report["active_source_rows"] = {
                    node_id: scalar(connection, "select count_big(*) from " + relation(manifest["sources"][node_id]))
                    for node_id in sorted(active_sources)
                }
                eligible = "order_qty > 0 and unit_price >= 0"
                bronze = tables["brnz_sales_orders"]
                report["sales"] = {
                    "bronze_all": sales_metrics(connection, bronze),
                    "bronze_eligible": sales_metrics(connection, bronze, eligible),
                    "silver": sales_metrics(connection, tables["slvr_sales_orders"]),
                }
                exclusion_sql = """select reason, count_big(*) as lines from (
                    select case when order_qty is null then 'quantity_null'
                        when order_qty <= 0 then 'quantity_nonpositive'
                        when unit_price is null then 'price_null'
                        when unit_price < 0 then 'price_negative' else 'eligible' end as reason
                    from {}) as classified group by reason""".format(bronze)
                report["bronze_eligibility"] = dict(connection.execute(text(exclusion_sql)).all())
                report["gold_totals"] = {}
                for model, quantity in (
                    ("gld_customer_metrics", "total_items_purchased"),
                    ("gld_product_performance", "total_quantity_sold"),
                    ("gld_sales_summary", "total_items_sold"),
                ):
                    sql = """select sum(cast(total_revenue as decimal(38,6))) as net_revenue,
                        sum(cast({} as bigint)) as quantity, sum(cast(total_orders as bigint)) as summed_order_counts
                        from {}""".format(quantity, tables[model])
                    report["gold_totals"][model] = dict(connection.execute(text(sql)).mappings().one())
                report["nonadditive_metrics"] = {
                    "gld_product_performance.summed_order_counts": (
                        "Diagnostic only: an order may contain multiple products; "
                        "never compare this sum to global distinct orders."
                    ),
                    "gld_sales_summary.unique_customers": "Per-date distinct counts are not additive across dates.",
                }
                report["dimensions_without_sales"] = {
                    model: scalar(connection, "select count_big(*) from " + tables[model] + " where total_orders = 0")
                    for model in ("gld_customer_metrics", "gld_product_performance")
                }

                def compare(name, expected, actual, tolerance=Decimal(0)):
                    matched = (expected is None and actual is None) or (
                        expected is not None
                        and actual is not None
                        and abs(Decimal(expected) - Decimal(actual)) <= tolerance
                    )
                    report["checks"].append({"check": name, "expected": expected, "actual": actual, "passed": matched})

                for name in ("brnz_customers", "brnz_products"):
                    compare(
                        name + "_rows_preserved",
                        report["model_rows"][name],
                        report["model_rows"][name.replace("brnz_", "slvr_")],
                    )
                for metric in ("lines", "orders", "quantity", "net_revenue"):
                    compare(
                        "eligible_bronze_to_silver." + metric,
                        report["sales"]["bronze_eligible"][metric],
                        report["sales"]["silver"][metric],
                    )
                for model, totals in report["gold_totals"].items():
                    for metric in ("quantity", "net_revenue"):
                        compare(
                            "silver_to_" + model + "." + metric,
                            report["sales"]["silver"][metric],
                            totals[metric],
                            Decimal("0.01") if metric == "net_revenue" else Decimal(0),
                        )
                    if model != "gld_product_performance":
                        compare(
                            "silver_to_" + model + ".orders",
                            report["sales"]["silver"]["orders"],
                            totals["summed_order_counts"],
                        )
                report["reconciliation_violations"] = {}
                for name, node in sorted(tests.items()):
                    sql = node["compiled_code"].strip().rstrip(";")
                    count = scalar(connection, "select count_big(*) from (" + sql + ") as violations")
                    report["reconciliation_violations"][name] = count
                    compare(name, 0, count)
                report["snapshot_finished_at_utc"] = now()
        passed = all(check["passed"] for check in report["checks"])
        report.update(status="passed" if passed else "failed", exit_code=0 if passed else 1)
    except Exception as error:
        report.update(status="error", exit_code=2, error_type=type(error).__name__)
    finally:
        if engine is not None:
            engine.dispose()
        report["finished_at_utc"] = now()
        (args.output_dir / "summary.json").write_text(
            json.dumps(report, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
        )
    print("Layer reconciliation {}. Evidence: {}".format(report["status"], args.output_dir), flush=True)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
