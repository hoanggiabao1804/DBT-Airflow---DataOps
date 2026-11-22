"""Check the actual Gold SQL with small, isolated SQL Server temporary tables.

Run inside the dbt container. These fixtures include multiple discounted lines
in one order, a free sale, and a customer/product with no sales. Closing the
connection removes every fixture; source tables and dbt relations are untouched.
"""

import argparse
import datetime as dt
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pyodbc
import yaml
from jinja2 import Environment, StrictUndefined


FIXTURES = """
SET NOCOUNT ON;
CREATE TABLE #customers (customer_id int, full_name varchar(30), territory_id int);
INSERT INTO #customers VALUES (1, 'Multiple lines', 1), (2, 'Free sale', 1), (3, 'No sales', 1);

CREATE TABLE #products (
    product_id int, product_name varchar(30), subcategory_name varchar(30),
    color varchar(10), list_price decimal(19,4), standard_cost decimal(19,4)
);
INSERT INTO #products VALUES
    (10, 'Paid product', 'Fixture', 'Blue', 10, 4),
    (20, 'Free product', 'Fixture', 'Blue', 0, 2),
    (30, 'Unsold product', 'Fixture', 'Blue', 5, 1);

CREATE TABLE #sales (
    customer_id int, product_id int, sales_order_id int, order_detail_id int,
    order_date datetime, order_qty smallint, unit_price decimal(19,4),
    line_total numeric(38,6), has_discount int, order_channel varchar(10)
);
INSERT INTO #sales VALUES
    (1, 10, 100, 1, '20200101', 2, 10, 18, 1, 'Online'),
    (1, 10, 100, 2, '20200101', 1, 5, 4, 1, 'Online'),
    (1, 10, 101, 3, '20200102', 1, 10, 10, 0, 'Offline'),
    (2, 20, 200, 4, '20200101', 1, 0, 0, 0, 'Offline');
"""

EXPECTED = {
    "gld_customer_metrics": (
        "customer_id",
        {
            1: {"total_orders": 2, "total_revenue": 32, "avg_order_value": 16, "orders_with_discount": 1},
            2: {"total_orders": 1, "total_revenue": 0, "avg_order_value": 0, "orders_with_discount": 0},
            3: {"total_orders": 0, "total_revenue": None, "avg_order_value": None, "orders_with_discount": 0},
        },
    ),
    "gld_sales_summary": (
        "order_date",
        {
            "2020-01-01": {
                "total_orders": 2,
                "online_orders": 1,
                "offline_orders": 1,
                "total_revenue": 22,
                "discounted_revenue": 22,
                "unique_customers": 2,
            },
            "2020-01-02": {
                "total_orders": 1,
                "online_orders": 0,
                "offline_orders": 1,
                "total_revenue": 10,
                "discounted_revenue": 0,
                "unique_customers": 1,
            },
        },
    ),
    "gld_product_performance": (
        "product_id",
        {
            10: {
                "total_orders": 2,
                "total_quantity_sold": 4,
                "total_revenue": 32,
                "total_profit": 16,
                "profit_margin_pct": 50,
            },
            20: {
                "total_orders": 1,
                "total_quantity_sold": 1,
                "total_revenue": 0,
                "total_profit": -2,
                "profit_margin_pct": None,
            },
            30: {
                "total_orders": 0,
                "total_quantity_sold": None,
                "total_revenue": None,
                "total_profit": None,
                "profit_margin_pct": 0,
            },
        },
    ),
}


def connection_string(project):
    project_config = yaml.safe_load((project / "dbt_project.yml").read_text())
    profile = yaml.safe_load((project / "profiles.yml").read_text())[project_config["profile"]]
    target = profile["outputs"][profile["target"]]
    if target.get("authentication", "sql") != "sql":
        raise ValueError("This local fixture runner expects the existing SQL authentication target.")

    def escaped(value):
        return "{" + str(value).replace("}", "}}") + "}"

    values = {
        "DRIVER": target["driver"],
        "SERVER": "{},{}".format(target["server"], target.get("port", 1433)),
        "DATABASE": target["database"],
        "UID": target["user"],
        "PWD": target["password"],
        "Encrypt": "yes" if target.get("encrypt", False) else "no",
        "TrustServerCertificate": "yes" if target.get("trust_cert", True) else "no",
    }
    return ";".join(key + "=" + escaped(value) for key, value in values.items())


def same_value(actual, expected):
    if actual is None or expected is None:
        return actual is expected
    return abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal("0.0001")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path("/usr/app/dbt"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output already exists; choose a new file to preserve evidence.")

    result = {"started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "checks": [], "status": "failed"}
    refs = {"slvr_customers": "#customers", "slvr_products": "#products", "slvr_sales_orders": "#sales"}
    template_env = Environment(undefined=StrictUndefined)
    connection = None
    try:
        connection = pyodbc.connect(connection_string(args.project_dir), autocommit=True, timeout=30)
        cursor = connection.cursor()
        cursor.execute(FIXTURES)
        while cursor.nextset():
            pass
        for model, (key, expected_rows) in EXPECTED.items():
            source = (args.project_dir / "models" / "gold" / (model + ".sql")).read_bytes()
            check = {"model": model, "sql_sha256": hashlib.sha256(source).hexdigest(), "mismatches": []}
            try:
                sql = template_env.from_string(source.decode("utf-8-sig")).render(
                    ref=lambda name: refs[name], config=lambda **kwargs: ""
                )
                cursor.execute(sql)
                columns = [item[0] for item in cursor.description]
                actual_rows = {}
                for row in cursor.fetchall():
                    record = dict(zip(columns, row))
                    row_key = record[key]
                    if isinstance(row_key, (dt.date, dt.datetime)):
                        row_key = row_key.isoformat()[:10]
                    if row_key in actual_rows:
                        check["mismatches"].append({"duplicate_key": row_key})
                    actual_rows[row_key] = record
                if set(actual_rows) != set(expected_rows):
                    check["mismatches"].append({"keys": "Missing or unexpected fixture rows"})
                for row_key, metrics in expected_rows.items():
                    if row_key not in actual_rows:
                        continue
                    for metric, expected in metrics.items():
                        actual = actual_rows[row_key][metric]
                        if not same_value(actual, expected):
                            check["mismatches"].append(
                                {"key": row_key, "metric": metric, "expected": expected, "actual": actual}
                            )
                check["status"] = "passed" if not check["mismatches"] else "failed"
            except pyodbc.Error as error:
                check.update(status="failed", error=str(error))
            result["checks"].append(check)
        result["status"] = "passed" if all(item["status"] == "passed" for item in result["checks"]) else "failed"
    finally:
        if connection is not None:
            connection.close()
        result["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        result["fixture_scope"] = "Connection-local #temporary tables; removed when the connection closes."
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "models": len(result["checks"]), "output": str(args.output)}))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
