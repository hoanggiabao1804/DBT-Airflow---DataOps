#!/usr/bin/env python3
"""Check that the deployed Bronze, Silver, and Gold relations are usable."""

import argparse
import os
import sys
from pathlib import Path

import pyodbc


# Fixed identifiers keep the queries independent of caller-controlled SQL text.
RELATIONS = (
    ("bronze", "brnz_customers"),
    ("bronze", "brnz_products"),
    ("bronze", "brnz_sales_orders"),
    ("silver", "slvr_customers"),
    ("silver", "slvr_products"),
    ("silver", "slvr_sales_orders"),
    ("gold", "gld_customer_metrics"),
    ("gold", "gld_product_performance"),
    ("gold", "gld_sales_summary"),
)

REQUIRED_KEYS = (
    ("silver", "slvr_customers", "customer_id"),
    ("silver", "slvr_products", "product_id"),
    ("silver", "slvr_sales_orders", "sales_order_id"),
    ("silver", "slvr_sales_orders", "order_detail_id"),
    ("gold", "gld_customer_metrics", "customer_id"),
    ("gold", "gld_product_performance", "product_id"),
    ("gold", "gld_sales_summary", "order_date"),
)


class SmokeTests:
    def __init__(self, server, database, user, password):
        def odbc_value(value):
            return "{" + str(value).replace("}", "}}") + "}"

        self.conn_string = (
            "DRIVER={ODBC Driver 17 for SQL Server};"
            f"SERVER={odbc_value(server)};DATABASE={odbc_value(database)};"
            f"UID={odbc_value(user)};PWD={odbc_value(password)};"
            "TrustServerCertificate=yes;"
        )
        self.connection = None

    def connect(self):
        try:
            self.connection = pyodbc.connect(self.conn_string, timeout=15)
            print("Database connection successful")
            return True
        except pyodbc.Error as error:
            print(f"Database connection failed: {error}")
            return False

    def check_relation(self, schema, table):
        name = f"{schema}.{table}"
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES " "WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?",
                schema,
                table,
            )
            if cursor.fetchone()[0] == 0:
                print(f"FAIL {name}: relation is missing")
                return False
            cursor.execute(f"SELECT COUNT_BIG(*) FROM [{schema}].[{table}]")
            count = cursor.fetchone()[0]
            if count < 1:
                print(f"FAIL {name}: relation is empty")
                return False
            print(f"PASS {name}: {count} rows")
            return True
        except pyodbc.Error as error:
            print(f"FAIL {name}: {error}")
            return False

    def check_key(self, schema, table, column):
        name = f"{schema}.{table}.{column}"
        try:
            cursor = self.connection.cursor()
            cursor.execute(f"SELECT COUNT_BIG(*) FROM [{schema}].[{table}] " f"WHERE [{column}] IS NULL")
            missing = cursor.fetchone()[0]
            if missing:
                print(f"FAIL {name}: {missing} NULL keys")
                return False
            print(f"PASS {name}: no NULL keys")
            return True
        except pyodbc.Error as error:
            print(f"FAIL {name}: {error}")
            return False

    def run_all_tests(self):
        passed = 0
        failed = 0
        available = set()
        print("Running deployment smoke tests")
        for schema, table in RELATIONS:
            if self.check_relation(schema, table):
                available.add((schema, table))
                passed += 1
            else:
                failed += 1

        for schema, table, column in REQUIRED_KEYS:
            if (schema, table) not in available:
                print(f"FAIL {schema}.{table}.{column}: relation unavailable")
                failed += 1
            elif self.check_key(schema, table, column):
                passed += 1
            else:
                failed += 1

        print(f"Smoke tests: {passed} passed, {failed} failed")
        return failed == 0

    def close(self):
        if self.connection:
            self.connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default=os.getenv("SMOKE_SQL_SERVER", "localhost"))
    parser.add_argument("--database", default=os.getenv("SMOKE_SQL_DATABASE", "AdventureWorks2014"))
    parser.add_argument("--user", default=os.getenv("SMOKE_SQL_USER", "sa"))
    parser.add_argument("--password", default=os.getenv("SMOKE_SQL_PASSWORD"))
    parser.add_argument("--from-dbt-profile", type=Path)
    args = parser.parse_args()
    if args.from_dbt_profile:
        import yaml

        profile = yaml.safe_load((args.from_dbt_profile / "profiles.yml").read_text(encoding="utf-8"))[
            "dbt_airflow_project"
        ]["outputs"]["dev"]
        values = [profile[key] for key in ("server", "database", "user", "password")]
        if any("{{" in str(value) for value in values):
            parser.error("--from-dbt-profile requires resolved dev credentials")
        args.server, args.database, args.user, args.password = values
    if not args.password:
        parser.error("set SMOKE_SQL_PASSWORD or pass --password")

    tests = SmokeTests(args.server, args.database, args.user, args.password)
    if not tests.connect():
        return 1
    try:
        return 0 if tests.run_all_tests() else 1
    finally:
        tests.close()


if __name__ == "__main__":
    sys.exit(main())
