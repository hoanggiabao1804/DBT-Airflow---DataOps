/*
  Tuan, week 1 / days 1-2: read-only baseline of the existing dbt models.
  Run after dbt run; obtain schema names from model_relations.json in the NEW
  evidence directory produced by scripts/verify_dbt_baseline.ps1.
  Do not use the old tracked dbt/target/manifest.json as runtime evidence.
  Example (credentials supplied separately, e.g. SQLCMDPASSWORD):
    sqlcmd -S localhost,1433 -U <user> -d AdventureWorks2014 -b -v BronzeSchema=dbo_bronze SilverSchema=dbo_silver GoldSchema=dbo_gold -i scripts/sql/review_dbt_models.sql
  This script changes no data or database objects and returns no personal data.
  issue_count counts affected rows/groups, not necessarily distinct source rows.
  KPI checks evaluate the business interpretation of an "order" (distinct ID).
  An issue is a review finding, not a sqlcmd error or an installed dbt test.
  Aggregate money comparisons allow an absolute difference of 0.01 per group.
*/
SET NOCOUNT ON;

-- 0. Source inventory and date coverage for the historical sample database.
SELECT 'source.rows.Sales.Customer' AS check_name, COUNT_BIG(*) AS actual_value
FROM [Sales].[Customer]
UNION ALL SELECT 'source.rows.Sales.SalesOrderHeader', COUNT_BIG(*) FROM [Sales].[SalesOrderHeader]
UNION ALL SELECT 'source.rows.Sales.SalesOrderDetail', COUNT_BIG(*) FROM [Sales].[SalesOrderDetail]
UNION ALL SELECT 'source.rows.Production.Product', COUNT_BIG(*) FROM [Production].[Product]
UNION ALL SELECT 'source.rows.Production.ProductSubcategory', COUNT_BIG(*) FROM [Production].[ProductSubcategory]
UNION ALL SELECT 'source.rows.Person.Person', COUNT_BIG(*) FROM [Person].[Person];

SELECT 'source.sales_order_date_coverage' AS check_name,
    MIN(OrderDate) AS earliest_order_date,
    MAX(OrderDate) AS latest_order_date,
    MAX(ModifiedDate) AS latest_header_modified_date
FROM [Sales].[SalesOrderHeader];

-- 1. Inventory: all 10 model relations must exist for this query to succeed.
SELECT 'rows.brnz_customers' AS check_name, COUNT_BIG(*) AS actual_value
FROM [$(BronzeSchema)].[brnz_customers]
UNION ALL SELECT 'rows.brnz_example', COUNT_BIG(*) FROM [$(BronzeSchema)].[brnz_example]
UNION ALL SELECT 'rows.brnz_products', COUNT_BIG(*) FROM [$(BronzeSchema)].[brnz_products]
UNION ALL SELECT 'rows.brnz_sales_orders', COUNT_BIG(*) FROM [$(BronzeSchema)].[brnz_sales_orders]
UNION ALL SELECT 'rows.slvr_customers', COUNT_BIG(*) FROM [$(SilverSchema)].[slvr_customers]
UNION ALL SELECT 'rows.slvr_products', COUNT_BIG(*) FROM [$(SilverSchema)].[slvr_products]
UNION ALL SELECT 'rows.slvr_sales_orders', COUNT_BIG(*) FROM [$(SilverSchema)].[slvr_sales_orders]
UNION ALL SELECT 'rows.gld_customer_metrics', COUNT_BIG(*) FROM [$(GoldSchema)].[gld_customer_metrics]
UNION ALL SELECT 'rows.gld_product_performance', COUNT_BIG(*) FROM [$(GoldSchema)].[gld_product_performance]
UNION ALL SELECT 'rows.gld_sales_summary', COUNT_BIG(*) FROM [$(GoldSchema)].[gld_sales_summary];

-- 2. Orders have one row per (sales_order_id, order_detail_id), not per order.
WITH bronze_duplicates AS (
    SELECT sales_order_id, order_detail_id
    FROM [$(BronzeSchema)].[brnz_sales_orders]
    GROUP BY sales_order_id, order_detail_id HAVING COUNT_BIG(*) > 1
), silver_duplicates AS (
    SELECT sales_order_id, order_detail_id
    FROM [$(SilverSchema)].[slvr_sales_orders]
    GROUP BY sales_order_id, order_detail_id HAVING COUNT_BIG(*) > 1
)
SELECT 'bronze.duplicate_order_line_keys' AS check_name, COUNT_BIG(*) AS issue_count
FROM bronze_duplicates
UNION ALL SELECT 'silver.duplicate_order_line_keys', COUNT_BIG(*) FROM silver_duplicates
UNION ALL
SELECT 'bronze.null_order_line_keys', COUNT_BIG(*)
FROM [$(BronzeSchema)].[brnz_sales_orders]
WHERE sales_order_id IS NULL OR order_detail_id IS NULL
UNION ALL
SELECT 'silver.null_order_line_keys', COUNT_BIG(*)
FROM [$(SilverSchema)].[slvr_sales_orders]
WHERE sales_order_id IS NULL OR order_detail_id IS NULL
UNION ALL
SELECT 'bronze.missing_customer_reference', COUNT_BIG(*)
FROM [$(BronzeSchema)].[brnz_sales_orders] s
WHERE NOT EXISTS (
    SELECT 1 FROM [$(BronzeSchema)].[brnz_customers] c WHERE c.CustomerID = s.customer_id
)
UNION ALL
SELECT 'bronze.missing_product_reference', COUNT_BIG(*)
FROM [$(BronzeSchema)].[brnz_sales_orders] s
WHERE NOT EXISTS (
    SELECT 1 FROM [$(BronzeSchema)].[brnz_products] p WHERE p.ProductID = s.product_id
)
UNION ALL
SELECT 'silver.missing_customer_reference', COUNT_BIG(*)
FROM [$(SilverSchema)].[slvr_sales_orders] s
WHERE NOT EXISTS (
    SELECT 1 FROM [$(SilverSchema)].[slvr_customers] c WHERE c.customer_id = s.customer_id
)
UNION ALL
SELECT 'silver.missing_product_reference', COUNT_BIG(*)
FROM [$(SilverSchema)].[slvr_sales_orders] s
WHERE NOT EXISTS (
    SELECT 1 FROM [$(SilverSchema)].[slvr_products] p WHERE p.product_id = s.product_id
);

-- 3. Silver intentionally keeps only positive quantities and nonnegative prices.
-- CASE also classifies NULL inputs as excluded, matching SQL WHERE semantics.
SELECT 'silver.rows_after_filter' AS check_name,
    (SELECT COUNT_BIG(*) FROM [$(BronzeSchema)].[brnz_sales_orders]
     WHERE order_qty > 0 AND unit_price >= 0) AS expected_value,
    (SELECT COUNT_BIG(*) FROM [$(SilverSchema)].[slvr_sales_orders]) AS actual_value;

SELECT 'bronze.rows_excluded_by_silver_filter' AS check_name, COUNT_BIG(*) AS actual_value
FROM [$(BronzeSchema)].[brnz_sales_orders]
WHERE CASE WHEN order_qty > 0 AND unit_price >= 0 THEN 1 ELSE 0 END = 0;

SELECT 'silver.unexpected_or_ineligible_order_lines' AS check_name, COUNT_BIG(*) AS issue_count
FROM [$(SilverSchema)].[slvr_sales_orders] s
WHERE NOT EXISTS (
    SELECT 1 FROM [$(BronzeSchema)].[brnz_sales_orders] b
    WHERE b.sales_order_id = s.sales_order_id AND b.order_detail_id = s.order_detail_id
      AND b.order_qty > 0 AND b.unit_price >= 0
)
UNION ALL
SELECT 'silver.missing_eligible_order_lines', COUNT_BIG(*)
FROM [$(BronzeSchema)].[brnz_sales_orders] b
WHERE b.order_qty > 0 AND b.unit_price >= 0
  AND NOT EXISTS (
      SELECT 1 FROM [$(SilverSchema)].[slvr_sales_orders] s
      WHERE s.sales_order_id = b.sales_order_id AND s.order_detail_id = b.order_detail_id
  )
UNION ALL
SELECT 'silver.invalid_quantity_or_price', COUNT_BIG(*)
FROM [$(SilverSchema)].[slvr_sales_orders]
WHERE order_qty IS NULL OR order_qty <= 0 OR unit_price IS NULL OR unit_price < 0
UNION ALL
SELECT 'silver.null_line_total', COUNT_BIG(*)
FROM [$(SilverSchema)].[slvr_sales_orders] WHERE line_total IS NULL;

-- 4. Revenue preservation, first globally then at the daily reporting grain.
WITH silver_total AS (
    SELECT COALESCE(SUM(CAST(line_total AS decimal(38, 6))), 0) AS revenue
    FROM [$(SilverSchema)].[slvr_sales_orders]
), gold_total AS (
    SELECT COALESCE(SUM(CAST(total_revenue AS decimal(38, 6))), 0) AS revenue
    FROM [$(GoldSchema)].[gld_sales_summary]
)
SELECT 'gold.sales_summary_total_revenue' AS check_name,
    s.revenue AS expected_value, g.revenue AS actual_value,
    CASE WHEN ABS(s.revenue - g.revenue) > 0.01 THEN 1 ELSE 0 END AS issue_count
FROM silver_total s CROSS JOIN gold_total g;

WITH expected AS (
    SELECT CAST(order_date AS date) AS order_date, 1 AS present,
        SUM(line_total) AS total_revenue,
        COUNT(DISTINCT sales_order_id) AS total_orders,
        COUNT(DISTINCT CASE WHEN order_channel = 'Online' THEN sales_order_id END) AS online_orders,
        COUNT(DISTINCT CASE WHEN order_channel = 'Offline' THEN sales_order_id END) AS offline_orders
    FROM [$(SilverSchema)].[slvr_sales_orders]
    GROUP BY CAST(order_date AS date)
), actual AS (
    SELECT *, 1 AS present FROM [$(GoldSchema)].[gld_sales_summary]
), comparisons AS (
    SELECT
        CASE WHEN e.present IS NULL OR a.present IS NULL THEN 1 ELSE 0 END AS missing_group,
        CASE WHEN ABS(e.total_revenue - a.total_revenue) > 0.01
               OR (e.total_revenue IS NULL AND a.total_revenue IS NOT NULL)
               OR (e.total_revenue IS NOT NULL AND a.total_revenue IS NULL)
             THEN 1 ELSE 0 END AS revenue_mismatch,
        CASE WHEN e.total_orders <> a.total_orders OR a.total_orders IS NULL THEN 1 ELSE 0 END AS order_mismatch,
        CASE WHEN e.online_orders <> a.online_orders OR a.online_orders IS NULL THEN 1 ELSE 0 END AS online_mismatch,
        CASE WHEN e.offline_orders <> a.offline_orders OR a.offline_orders IS NULL THEN 1 ELSE 0 END AS offline_mismatch
    FROM expected e FULL OUTER JOIN actual a
      ON e.order_date = a.order_date OR (e.order_date IS NULL AND a.order_date IS NULL)
)
SELECT 'gold.daily_missing_or_extra_groups' AS check_name, COUNT_BIG(*) AS issue_count
FROM comparisons WHERE missing_group = 1
UNION ALL SELECT 'gold.daily_revenue_mismatch', COUNT_BIG(*) FROM comparisons WHERE missing_group = 1 OR revenue_mismatch = 1
UNION ALL SELECT 'gold.daily_total_orders_mismatch', COUNT_BIG(*) FROM comparisons WHERE missing_group = 1 OR order_mismatch = 1
UNION ALL SELECT 'gold.daily_online_orders_mismatch', COUNT_BIG(*) FROM comparisons WHERE missing_group = 1 OR online_mismatch = 1
UNION ALL SELECT 'gold.daily_offline_orders_mismatch', COUNT_BIG(*) FROM comparisons WHERE missing_group = 1 OR offline_mismatch = 1;

-- Daily customer/product dimensions are not additive; these order counts are
-- additive because an order has one date, customer and channel in this source.
SELECT 'gold.online_orders' AS check_name,
    (SELECT COUNT_BIG(DISTINCT sales_order_id) FROM [$(SilverSchema)].[slvr_sales_orders]
     WHERE order_channel = 'Online') AS expected_value,
    (SELECT SUM(CAST(online_orders AS bigint)) FROM [$(GoldSchema)].[gld_sales_summary]) AS actual_value
UNION ALL
SELECT 'gold.offline_orders',
    (SELECT COUNT_BIG(DISTINCT sales_order_id) FROM [$(SilverSchema)].[slvr_sales_orders] WHERE order_channel = 'Offline'),
    (SELECT SUM(CAST(offline_orders AS bigint)) FROM [$(GoldSchema)].[gld_sales_summary])
UNION ALL
SELECT 'gold.customer_orders_with_discount',
    (SELECT COUNT_BIG(DISTINCT sales_order_id) FROM [$(SilverSchema)].[slvr_sales_orders] WHERE has_discount = 1),
    (SELECT SUM(CAST(orders_with_discount AS bigint)) FROM [$(GoldSchema)].[gld_customer_metrics]);

-- 5. Customer AOV means revenue / distinct orders; AVG(line_total) is line AOV.
-- Compare both definitions and explicitly retain NULL for customers with no sales.
WITH expected AS (
    SELECT c.customer_id, 1 AS present,
        SUM(CAST(s.line_total AS decimal(28, 6))) / NULLIF(COUNT(DISTINCT s.sales_order_id), 0) AS avg_order_value,
        AVG(s.line_total) AS avg_line_value,
        COUNT(DISTINCT CASE WHEN s.has_discount = 1 THEN s.sales_order_id END) AS orders_with_discount
    FROM [$(SilverSchema)].[slvr_customers] c
    LEFT JOIN [$(SilverSchema)].[slvr_sales_orders] s ON c.customer_id = s.customer_id
    GROUP BY c.customer_id
), actual AS (
    SELECT *, 1 AS present FROM [$(GoldSchema)].[gld_customer_metrics]
), comparisons AS (
    SELECT
        CASE WHEN e.present IS NULL OR a.present IS NULL THEN 1 ELSE 0 END AS missing_group,
        CASE WHEN ABS(e.avg_order_value - a.avg_order_value) > 0.01
               OR (e.avg_order_value IS NULL AND a.avg_order_value IS NOT NULL)
               OR (e.avg_order_value IS NOT NULL AND a.avg_order_value IS NULL)
             THEN 1 ELSE 0 END AS order_aov_mismatch,
        CASE WHEN ABS(e.avg_line_value - a.avg_order_value) > 0.01
               OR (e.avg_line_value IS NULL AND a.avg_order_value IS NOT NULL)
               OR (e.avg_line_value IS NOT NULL AND a.avg_order_value IS NULL)
             THEN 1 ELSE 0 END AS line_aov_mismatch,
        CASE WHEN e.orders_with_discount <> a.orders_with_discount OR a.orders_with_discount IS NULL
             THEN 1 ELSE 0 END AS discount_mismatch
    FROM expected e FULL OUTER JOIN actual a ON e.customer_id = a.customer_id
)
SELECT 'gold.customer_missing_or_extra_groups' AS check_name, COUNT_BIG(*) AS issue_count
FROM comparisons WHERE missing_group = 1
UNION ALL SELECT 'gold.customer_aov_vs_order_definition', COUNT_BIG(*) FROM comparisons WHERE missing_group = 1 OR order_aov_mismatch = 1
UNION ALL SELECT 'gold.customer_aov_vs_current_line_formula', COUNT_BIG(*) FROM comparisons WHERE missing_group = 1 OR line_aov_mismatch = 1
UNION ALL SELECT 'gold.customer_discount_order_mismatch', COUNT_BIG(*) FROM comparisons WHERE missing_group = 1 OR discount_mismatch = 1;

-- 6. The product margin guard uses quantity > 0, but divides by revenue.
-- Count risky products without evaluating the unsafe division itself.
WITH product_totals AS (
    SELECT p.product_id, SUM(s.order_qty) AS quantity, SUM(s.line_total) AS revenue
    FROM [$(SilverSchema)].[slvr_products] p
    LEFT JOIN [$(SilverSchema)].[slvr_sales_orders] s ON p.product_id = s.product_id
    GROUP BY p.product_id
)
SELECT 'gold.product_margin_zero_revenue_risk' AS check_name, COUNT_BIG(*) AS issue_count
FROM product_totals WHERE quantity > 0 AND revenue = 0;
