#!/usr/bin/env bash
# Data-quality alert drill: build a corrupted COPY of Silver in schema dq_drill,
# so ge_data_quality can be pointed at it (param schema=dq_drill) and must fail
# with a critical alert. Real Silver tables are never modified.
#
#   ./scripts/dq_drill.sh setup      # create dq_drill.slvr_customers / slvr_sales_orders + inject defects
#   ./scripts/dq_drill.sh status     # show injected defect counts
#   ./scripts/dq_drill.sh teardown   # drop the schema again
#
# Defects (each maps to one GX expectation):
#   customers: 25 rows email_promotion = 9        -> expect_column_values_to_be_in_set
#   orders   : 40 rows order_qty = 0              -> expect_column_values_to_be_between (strict_min)
#   orders   : 15 rows order_channel = 'Fax'      -> expect_column_values_to_be_in_set
#
# Override the Compose command with DC="docker compose -p ... -f ..." if needed.
set -euo pipefail

DC=${DC:-"docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml"}
SA_PASSWORD=${SQLSERVER_SA_PASSWORD:-YourStrong@Passw0rd}
DB=AdventureWorks2014

sql() {
    # Password goes through the container environment, not the command line.
    SQLCMDPASSWORD="$SA_PASSWORD" $DC exec -T -e SQLCMDPASSWORD sqlserver \
        /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -d "$DB" -b -h -1 -W -Q "SET NOCOUNT ON; $1"
}

case "${1:-}" in
setup)
    sql "IF SCHEMA_ID('dq_drill') IS NULL EXEC('CREATE SCHEMA dq_drill');
         DROP TABLE IF EXISTS dq_drill.slvr_customers; DROP TABLE IF EXISTS dq_drill.slvr_sales_orders;
         SELECT * INTO dq_drill.slvr_customers FROM silver.slvr_customers;
         SELECT * INTO dq_drill.slvr_sales_orders FROM silver.slvr_sales_orders;
         UPDATE TOP (25) dq_drill.slvr_customers SET email_promotion = 9;
         UPDATE TOP (40) dq_drill.slvr_sales_orders SET order_qty = 0;
         UPDATE TOP (15) dq_drill.slvr_sales_orders SET order_channel = 'Fax' WHERE order_qty <> 0;"
    echo "dq_drill schema created with injected defects"
    "$0" status
    ;;
status)
    sql "SELECT 'customers.email_promotion_invalid', COUNT(*) FROM dq_drill.slvr_customers WHERE email_promotion NOT IN (0,1,2)
         UNION ALL SELECT 'orders.order_qty_zero', COUNT(*) FROM dq_drill.slvr_sales_orders WHERE order_qty <= 0
         UNION ALL SELECT 'orders.order_channel_invalid', COUNT(*) FROM dq_drill.slvr_sales_orders
                   WHERE order_channel NOT IN ('Online','Offline')"
    ;;
teardown)
    sql "DROP TABLE IF EXISTS dq_drill.slvr_customers; DROP TABLE IF EXISTS dq_drill.slvr_sales_orders;
         IF SCHEMA_ID('dq_drill') IS NOT NULL EXEC('DROP SCHEMA dq_drill');"
    echo "dq_drill schema removed"
    ;;
*)
    echo "usage: $0 setup|status|teardown" >&2
    exit 2
    ;;
esac
