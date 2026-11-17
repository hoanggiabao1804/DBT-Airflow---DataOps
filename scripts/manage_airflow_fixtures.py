"""Own isolated SQL fixtures for Airflow quality integration checks.

Run inside ge-worker through ``docker exec -i``. The process creates its own UUID
schema and keeps ownership until cleanup, including when its stdin closes. No
caller-supplied schema can be claimed or dropped, and Silver is never modified.
"""

import argparse
import json
from pathlib import Path
import signal
import sys
import uuid

from sqlalchemy import Column, MetaData, Table, create_engine, text

from run_ge_checkpoints import load_connection
from verify_ge_contracts import CUSTOMER_COLUMNS, ORDER_COLUMNS, fixture_cases

PREFIX = "FIXTURE_EVENT "


def emit(event, **values):
    print(PREFIX + json.dumps(dict(event=event, **values), sort_keys=True), flush=True)


def terminate(_signum, _frame):
    raise SystemExit(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", type=Path, default=Path("/workspace/dbt"))
    parser.add_argument("--target", default="dev")
    args = parser.parse_args()
    signal.signal(signal.SIGTERM, terminate)
    schema = "ge_airflow_" + uuid.uuid4().hex
    engine, claimed, cleaned = None, False, False
    failed = False
    try:
        engine = create_engine(load_connection(args.project_dir, args.target))
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
        cases = {case["name"]: case for case in fixture_cases()}
        selected = {
            "load_valid": cases["valid_nullable_free_discount_multiline"],
            "load_invalid": cases["invalid_domains"],
        }
        emit("ready", schema=schema)
        for line in sys.stdin:
            action = json.loads(line)["action"]
            if action == "cleanup":
                break
            if action in selected:
                case = selected[action]
                with engine.begin() as connection:
                    for table, rows in zip(tables, (case["customers"], case["orders"])):
                        connection.execute(table.delete())
                        if rows:
                            connection.execute(table.insert(), rows)
                emit(
                    "loaded",
                    action=action,
                    schema=schema,
                    expected_failures=case["failures"],
                    expected_rows={"customer_nonempty": len(case["customers"]), "order_nonempty": len(case["orders"])},
                )
            elif action == "drop_order":
                with engine.begin() as connection:
                    tables[1].drop(connection)
                emit("loaded", action=action, schema=schema)
            else:
                raise ValueError("Unknown fixture action")
    except Exception as error:
        failed = True
        # SQL exception messages can contain credentials or values; export type only.
        emit("error", error_type=type(error).__name__)
    finally:
        if claimed:
            try:
                with engine.begin() as connection:
                    for table in reversed(tables):
                        table.drop(connection, checkfirst=True)
                    # Unknown objects prevent schema removal; never drop them.
                    connection.execute(text("DROP SCHEMA [" + schema + "]"))
                engine.dispose()
                with engine.connect() as connection:
                    cleaned = not connection.execute(
                        text("SELECT COUNT(*) FROM sys.schemas WHERE name = :name"), {"name": schema}
                    ).scalar()
            except Exception as error:
                failed = True
                emit("cleanup_error", error_type=type(error).__name__)
        if engine is not None:
            engine.dispose()
        emit("closed", schema=schema, cleanup_verified=cleaned)
    return 0 if cleaned and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
