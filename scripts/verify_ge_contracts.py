"""Verify the checked-in GX suites against isolated SQL Server fixture tables.

Run in the Great Expectations image, with run_ge_checkpoints.py alongside this
file. All writes use a newly claimed UUID schema; actual Silver data is read by
neither the setup nor the cleanup. Fixture validation failures are intentional.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid

from sqlalchemy import Column, DateTime, Integer, MetaData, Numeric, Table, Unicode, create_engine, text

from run_ge_checkpoints import load_connection, run_checkpoints


CUSTOMER_COLUMNS = {
    "customer_id": Integer,
    "first_name": Unicode(80),
    "last_name": Unicode(80),
    "full_name": Unicode(160),
    "email_promotion": Integer,
    "store_id": Integer,
    "territory_id": Integer,
    "last_modified_date": DateTime,
}
ORDER_COLUMNS = {
    "sales_order_id": Integer,
    "order_detail_id": Integer,
    "order_date": DateTime,
    "due_date": DateTime,
    "ship_date": DateTime,
    "status": Integer,
    "order_channel": Unicode(20),
    "sales_order_number": Unicode(30),
    "purchase_order_number": Unicode(30),
    "customer_id": Integer,
    "sales_person_id": Integer,
    "territory_id": Integer,
    "product_id": Integer,
    "order_qty": Integer,
    "unit_price": Numeric(19, 6),
    "unit_price_discount": Numeric(19, 6),
    "line_total": Numeric(19, 6),
    "gross_amount": Numeric(19, 6),
    "effective_unit_price": Numeric(19, 6),
    "has_discount": Integer,
}
CUSTOMER_REQUIRED = ("customer_id", "first_name", "last_name", "full_name", "last_modified_date")
ORDER_OPTIONAL = ("ship_date", "purchase_order_number", "sales_person_id", "territory_id")


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def fixture_cases():
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    customer = dict.fromkeys(CUSTOMER_COLUMNS)
    customer.update(
        customer_id=1,
        first_name="Unknown",
        last_name="Unknown",
        full_name="Unknown Unknown",
        last_modified_date=now - timedelta(days=1),
    )
    order = dict.fromkeys(ORDER_COLUMNS)
    order.update(
        sales_order_id=1,
        order_detail_id=1,
        order_date=now - timedelta(days=2),
        due_date=now + timedelta(days=7),
        status=1,
        order_channel="Online",
        sales_order_number="FIXTURE-1",
        customer_id=1,
        product_id=1,
        order_qty=1,
        unit_price=10,
        unit_price_discount=0,
        line_total=10,
        gross_amount=10,
        effective_unit_price=10,
        has_discount=0,
    )
    cases = []

    def add(name, customers, orders, failures, cli=False):
        cases.append({"name": name, "customers": customers, "orders": orders, "failures": failures, "cli": cli})

    valid_customers = [
        dict(customer, customer_id=i + 1, email_promotion=value) for i, value in enumerate([None, 0, 1, 2])
    ]
    valid_orders = [
        dict(order, order_detail_id=i, status=i, order_channel="Online" if i % 2 else "Offline") for i in range(1, 7)
    ]
    valid_orders[0].update(unit_price=0, line_total=0, gross_amount=0, effective_unit_price=0)
    valid_orders[1].update(unit_price_discount=1, line_total=0, effective_unit_price=0, has_discount=1)
    valid_orders[2].update(ship_date=now - timedelta(days=1))
    add("valid_nullable_free_discount_multiline", valid_customers, valid_orders, {}, cli=True)
    add(
        "duplicate_keys",
        [customer, deepcopy(customer)],
        [order, deepcopy(order)],
        {
            "customer_id_unique": 2,
            "order_key_unique": 2,
        },
    )
    null_customer, null_order = deepcopy(customer), deepcopy(order)
    null_customer.update(dict.fromkeys(CUSTOMER_REQUIRED))
    null_order.update(dict.fromkeys(set(ORDER_COLUMNS) - set(ORDER_OPTIONAL)))
    failures = {"customer_" + column + "_not_null": 1 for column in CUSTOMER_REQUIRED}
    # The customer ID rule deliberately has a shorter stable identifier.
    failures["customer_id_not_null"] = failures.pop("customer_customer_id_not_null")
    failures.update({"order_" + column + "_not_null": 1 for column in ORDER_COLUMNS if column not in ORDER_OPTIONAL})
    add("required_nulls", [null_customer], [null_order], failures)
    add(
        "invalid_domains",
        [dict(customer, email_promotion=3)],
        [dict(order, status=7, order_channel="Invalid", has_discount=2)],
        {
            "customer_email_promotion_allowed": 1,
            "order_status_allowed": 1,
            "order_channel_allowed": 1,
            "order_has_discount_allowed": 1,
        },
    )
    low = dict(
        order,
        order_qty=0,
        unit_price=-1,
        line_total=-1,
        gross_amount=-1,
        effective_unit_price=-1,
        unit_price_discount=-0.1,
    )
    high = dict(order, order_detail_id=2, order_qty=-1, unit_price_discount=1.01)
    add(
        "invalid_numeric_ranges",
        [customer],
        [low, high],
        {
            "order_qty_positive": 2,
            "order_discount_range": 2,
            "order_unit_price_nonnegative": 1,
            "order_line_total_nonnegative": 1,
            "order_gross_amount_nonnegative": 1,
            "order_effective_unit_price_nonnegative": 1,
        },
    )
    future = now + timedelta(days=2)
    add(
        "future_timestamps",
        [dict(customer, last_modified_date=future)],
        [dict(order, order_date=future, ship_date=future)],
        {
            "customer_last_modified_date_not_future": 1,
            "order_order_date_not_future": 1,
            "order_ship_date_not_future": 1,
        },
    )
    add("empty_tables", [], [], {"customer_nonempty": None, "order_nonempty": None}, cli=True)
    return cases


def execute_case(args, schema, output, connection_url, case):
    destination = output / case["name"]
    if case["cli"]:
        command = [
            sys.executable,
            str(Path(__file__).with_name("run_ge_checkpoints.py")),
            "--project-dir",
            str(args.project_dir),
            "--config-dir",
            str(args.config_dir),
            "--output-dir",
            str(destination),
            "--target",
            args.target,
            "--schema",
            schema,
        ]
        process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
        (output / (case["name"] + ".stdout.log")).write_text(process.stdout, encoding="utf-8")
        result = json.loads((destination / "summary.json").read_text(encoding="utf-8"))
        return result, process.returncode
    result = run_checkpoints(args.config_dir, destination, connection_url, schema)
    return result, result["exit_code"]


def assert_result(case, result, native_exit, expected_rules):
    checks = [check for validation in result["validations"] for check in validation["checks"]]
    ids = [check["rule_id"] for check in checks]
    actual = {check["rule_id"]: check.get("unexpected_count") for check in checks if not check["success"]}
    failures = case["failures"]
    expected_counts = {"customer_nonempty": len(case["customers"]), "order_nonempty": len(case["orders"])}
    actual_counts = {
        check["rule_id"]: check.get("observed_value") for check in checks if check["rule_id"] in expected_counts
    }
    code = 1 if failures else 0
    expected_status = "failed" if failures else "passed"
    matched = (
        len(ids) == len(expected_rules)
        and set(ids) == expected_rules
        and actual == failures
        and result["status"] == expected_status
        and result["exit_code"] == code
        and native_exit == code
        and actual_counts == expected_counts
    )
    return {
        "case": case["name"],
        "expected_failures": failures,
        "actual_failures": actual,
        "expected_row_counts": expected_counts,
        "actual_row_counts": actual_counts,
        "expected_exit_code": code,
        "actual_exit_code": native_exit,
        "native_cli": case["cli"],
        "checks_evaluated": len(checks),
        "matched": matched,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path("/workspace/dbt"))
    parser.add_argument("--config-dir", type=Path, default=Path("/workspace/great_expectations"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--target", default="dev")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("Output directory must be new or empty; existing evidence is preserved")
    output.mkdir(parents=True, exist_ok=True)
    schema = "ge_contracts_" + uuid.uuid4().hex
    summary = {
        "started_at_utc": utc_now(),
        "status": "running",
        "fixture_schema": schema,
        "contracts": [],
        "cleanup_verified": False,
        "config_sha256": {},
    }
    write_json(output / "summary.json", summary)
    engine, claimed = None, False
    try:
        expected_rules = set()
        for relative in (
            "great_expectations.yml",
            "expectations/customer_suite.json",
            "expectations/order_suite.json",
            "checkpoints/customer_checkpoint.yml",
            "checkpoints/order_checkpoint.yml",
        ):
            content = (args.config_dir / relative).read_bytes()
            summary["config_sha256"][relative] = hashlib.sha256(content).hexdigest()
            if relative.startswith("expectations/"):
                expected_rules.update(item["meta"]["rule_id"] for item in json.loads(content)["expectations"])
        connection_url = load_connection(args.project_dir, args.target)
        engine = create_engine(connection_url)
        metadata = MetaData(schema=schema)
        tables = [
            Table(name, metadata, *(Column(column, kind, nullable=True) for column, kind in columns.items()))
            for name, columns in (("slvr_customers", CUSTOMER_COLUMNS), ("slvr_sales_orders", ORDER_COLUMNS))
        ]
        with engine.begin() as connection:
            if connection.execute(
                text("SELECT COUNT(*) FROM sys.schemas WHERE name = :name"), {"name": schema}
            ).scalar():
                raise RuntimeError("Fixture schema already exists; refusing to claim it")
            connection.execute(text("CREATE SCHEMA [" + schema + "]"))
        claimed = True
        with engine.begin() as connection:
            metadata.create_all(connection)
        for case in fixture_cases():
            with engine.begin() as connection:
                for table, rows in zip(tables, (case["customers"], case["orders"])):
                    connection.execute(table.delete())
                    if rows:
                        connection.execute(table.insert(), rows)
            result, native_exit = execute_case(args, schema, output, connection_url, case)
            assertion = assert_result(case, result, native_exit, expected_rules)
            summary["contracts"].append(assertion)
            write_json(output / "summary.json", summary)
            if not assertion["matched"]:
                raise RuntimeError("Fixture assertion mismatch: " + case["name"])
        with engine.begin() as connection:
            tables[1].drop(connection)
        case = {"name": "missing_table_runtime_error", "cli": True}
        result, native_exit = execute_case(args, schema, output, connection_url, case)
        summary["contracts"].append(
            {
                "case": case["name"],
                "expected_exit_code": 2,
                "actual_exit_code": native_exit,
                "native_cli": True,
                "expected_status": "error",
                "actual_status": result["status"],
                "matched": native_exit == 2 and result["exit_code"] == 2 and result["status"] == "error",
            }
        )
        summary["status"] = "passed" if all(item["matched"] for item in summary["contracts"]) else "failed"
    except Exception as error:
        # Connection exceptions can include credentials; keep diagnostic types only.
        summary.update(status="failed", error_type=type(error).__name__)
    finally:
        if claimed:
            try:
                with engine.begin() as connection:
                    for table in reversed(tables):
                        table.drop(connection, checkfirst=True)
                    # Unknown objects make DROP SCHEMA fail; they are never deleted.
                    connection.execute(text("DROP SCHEMA [" + schema + "]"))
                engine.dispose()
                with engine.connect() as connection:
                    remaining = connection.execute(
                        text("SELECT COUNT(*) FROM sys.schemas WHERE name = :name"), {"name": schema}
                    ).scalar()
                    summary["cleanup_verified"] = remaining == 0
            except Exception as error:
                summary["cleanup_error_type"] = type(error).__name__
        if engine is not None:
            engine.dispose()
        if not summary["cleanup_verified"]:
            summary["status"] = "failed"
        summary["finished_at_utc"] = utc_now()
        write_json(output / "summary.json", summary)
    print("GX fixture contracts {}. Evidence: {}".format(summary["status"], output), flush=True)
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
