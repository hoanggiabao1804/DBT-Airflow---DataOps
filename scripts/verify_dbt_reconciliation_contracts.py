"""Verify day 13 reconciliation SQL rejects deliberately corrupted fixture data.

Run inside the dbt container beside verify_dbt_gold_contracts.py. All tables are
connection-local #temporary tables. Each mutation is rolled back before the next
case; no business relation is written. Only counts and hashes enter the report.
"""

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

import pyodbc
from jinja2 import Environment, StrictUndefined

from verify_dbt_gold_contracts import FIXTURES, connection_string

TESTS = {
    "customers": "assert_silver_customer_preservation",
    "products": "assert_silver_product_preservation",
    "customer_metrics": "assert_customer_metrics_reconciliation",
    "daily_sales": "assert_daily_sales_reconciliation",
    "product_metrics": "assert_product_metrics_reconciliation",
}
REFS = {
    "brnz_customers": "#bronze_customers",
    "brnz_products": "#bronze_products",
    "slvr_customers": "#customers",
    "slvr_products": "#products",
    "slvr_sales_orders": "#sales",
    "gld_customer_metrics": "#gold_customers",
    "gld_sales_summary": "#gold_daily",
    "gld_product_performance": "#gold_products",
}
MUTATIONS = [
    ("missing_customer", "customers", "DELETE FROM #customers WHERE customer_id = 3", 1),
    ("extra_customer", "customers", "INSERT INTO #customers VALUES (4, 'Extra', 1)", 1),
    ("replaced_customer_key", "customers", "UPDATE #customers SET customer_id = 4 WHERE customer_id = 3", 2),
    ("missing_product", "products", "DELETE FROM #products WHERE product_id = 30", 1),
    ("extra_product", "products", "INSERT INTO #products VALUES (40, 'Extra', 'Fixture', 'Blue', 5, 1)", 1),
    ("replaced_product_key", "products", "UPDATE #products SET product_id = 40 WHERE product_id = 30", 2),
    (
        "customer_items",
        "customer_metrics",
        "UPDATE #gold_customers SET total_items_purchased = total_items_purchased + 1 WHERE customer_id = 1",
        1,
    ),
    (
        "customer_first_date",
        "customer_metrics",
        "UPDATE #gold_customers SET first_order_date = DATEADD(day, -1, first_order_date) WHERE customer_id = 1",
        1,
    ),
    (
        "customer_last_date",
        "customer_metrics",
        "UPDATE #gold_customers SET last_order_date = DATEADD(day, 1, last_order_date) WHERE customer_id = 1",
        1,
    ),
    (
        "daily_customers",
        "daily_sales",
        "UPDATE #gold_daily SET unique_customers = unique_customers + 1 WHERE order_date = '20200101'",
        1,
    ),
    (
        "daily_items",
        "daily_sales",
        "UPDATE #gold_daily SET total_items_sold = total_items_sold + 1 WHERE order_date = '20200101'",
        1,
    ),
    (
        "daily_line_average",
        "daily_sales",
        "UPDATE #gold_daily SET avg_order_line_value = avg_order_line_value + 1 WHERE order_date = '20200101'",
        1,
    ),
    (
        "daily_discount_revenue",
        "daily_sales",
        "UPDATE #gold_daily SET discounted_revenue = discounted_revenue + 1 WHERE order_date = '20200101'",
        1,
    ),
    (
        "product_selling_price",
        "product_metrics",
        "UPDATE #gold_products SET avg_selling_price = avg_selling_price + 1 WHERE product_id = 10",
        1,
    ),
    (
        "no_sales_customer_null_items",
        "customer_metrics",
        "UPDATE #gold_customers SET total_items_purchased = 0 WHERE customer_id = 3",
        1,
    ),
    (
        "no_sales_product_null_price",
        "product_metrics",
        "UPDATE #gold_products SET avg_selling_price = 0 WHERE product_id = 30",
        1,
    ),
    (
        "offsetting_daily_revenue",
        "daily_sales",
        "UPDATE #gold_daily SET total_revenue = total_revenue + CASE WHEN order_date = '20200101' THEN 1 ELSE -1 END",
        2,
    ),
]


def execute_batch(cursor, sql):
    """Consume batch result sets before issuing another statement."""
    cursor.execute(sql)
    while cursor.nextset():
        pass


def render_file(path, environment, hashes, root):
    source = path.read_bytes()
    hashes[str(path.relative_to(root)).replace("\\", "/")] = hashlib.sha256(source).hexdigest()
    return environment.from_string(source.decode("utf-8-sig")).render(
        ref=lambda name: REFS[name], config=lambda **kwargs: ""
    )


def run_check(cursor, sql, name, test, expected):
    cursor.execute(sql)
    actual = len(cursor.fetchall())
    return {
        "case": name,
        "test": TESTS[test],
        "expected_mismatch_rows": expected,
        "actual_mismatch_rows": actual,
        "status": "passed" if actual == expected else "failed",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path("/usr/app/dbt"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; use a new path to preserve evidence.")

    result = {
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "error",
        "checks": [],
        "input_sha256": {},
        "cleanup_verified": False,
        "fixture_scope": "Connection-local temporary tables; each mutation rolled back; no business writes.",
        "baseline_cases": "Multiple lines/order, discounts, free sale, customer/product with no sales.",
    }
    result["runner_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result["fixture_helper_sha256"] = hashlib.sha256(
        Path(__file__).with_name("verify_dbt_gold_contracts.py").read_bytes()
    ).hexdigest()
    connection = None
    phase = "connect"
    try:
        connection = pyodbc.connect(connection_string(args.project_dir), autocommit=True, timeout=30)
        cursor = connection.cursor()
        phase = "prepare fixtures"
        execute_batch(cursor, FIXTURES)
        execute_batch(
            cursor,
            "SELECT customer_id AS CustomerID INTO #bronze_customers FROM #customers; "
            "SELECT product_id AS ProductID INTO #bronze_products FROM #products;",
        )
        environment = Environment(undefined=StrictUndefined)
        for model in ("gld_customer_metrics", "gld_sales_summary", "gld_product_performance"):
            sql = render_file(
                args.project_dir / "models" / "gold" / (model + ".sql"),
                environment,
                result["input_sha256"],
                args.project_dir,
            )
            # Materialize the actual model's final CTE into an isolated temp table.
            sql, count = re.subn(
                r"select\s+\*\s+from\s+(\w+)\s*;?\s*$",
                lambda match, name=model: "select * into " + REFS[name] + " from " + match.group(1),
                sql,
                flags=re.IGNORECASE,
            )
            if count != 1:
                raise ValueError("Gold model final projection is unsupported by the fixture materializer.")
            execute_batch(cursor, sql)
        sql_tests = {
            key: render_file(
                args.project_dir / "tests" / "data_quality" / (name + ".sql"),
                environment,
                result["input_sha256"],
                args.project_dir,
            )
            for key, name in TESTS.items()
        }
        for key, sql in sql_tests.items():
            phase = "baseline " + key
            result["checks"].append(run_check(cursor, sql, phase, key, 0))
        for name, key, mutation, expected in MUTATIONS:
            phase = "mutation " + name
            execute_batch(cursor, "BEGIN TRANSACTION")
            try:
                execute_batch(cursor, mutation)
                result["checks"].append(run_check(cursor, sql_tests[key], name, key, expected))
            finally:
                execute_batch(cursor, "IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
        # Prove mutation rollback restored every tested relation before cleanup.
        for key, sql in sql_tests.items():
            phase = "restored " + key
            result["checks"].append(run_check(cursor, sql, phase, key, 0))
        result["status"] = "passed" if all(check["status"] == "passed" for check in result["checks"]) else "failed"
    except Exception as error:  # Report safe context, never connection strings or SQL row data.
        result.update(status="error", error_type=type(error).__name__, error_phase=phase)
    finally:
        if connection is not None:
            try:
                cursor = connection.cursor()
                execute_batch(cursor, "IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION")
                for table in reversed(list(REFS.values())):
                    execute_batch(cursor, "IF OBJECT_ID('tempdb.." + table + "') IS NOT NULL DROP TABLE " + table)
                cursor.execute("SELECT " + ", ".join("OBJECT_ID('tempdb.." + table + "')" for table in REFS.values()))
                result["cleanup_verified"] = all(value is None for value in cursor.fetchone())
                if not result["cleanup_verified"]:
                    result["status"] = "error"
            except Exception as error:
                result.update(status="error", cleanup_error_type=type(error).__name__)
            finally:
                connection.close()
        result["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        result["case_count"] = len(result["checks"])
        result["passed_cases"] = sum(check["status"] == "passed" for check in result["checks"])
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
    print(json.dumps({key: result[key] for key in ("status", "case_count", "passed_cases", "cleanup_verified")}))
    return {"passed": 0, "failed": 1, "error": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
