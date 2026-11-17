{{ config(tags=['data_quality', 'reconciliation']) }}

-- One Gold row must exist per Silver order date. Channel metrics count orders,
-- not order lines. Compare each date independently so offsetting errors fail.
select
    coalesce(expected.order_date, actual.order_date) as order_date,
    expected.total_orders as expected_total_orders,
    actual.total_orders as actual_total_orders,
    expected.online_orders as expected_online_orders,
    actual.online_orders as actual_online_orders,
    expected.offline_orders as expected_offline_orders,
    actual.offline_orders as actual_offline_orders,
    expected.total_revenue as expected_total_revenue,
    actual.total_revenue as actual_total_revenue,
    expected.unique_customers as expected_unique_customers,
    actual.unique_customers as actual_unique_customers,
    expected.total_items_sold as expected_total_items_sold,
    actual.total_items_sold as actual_total_items_sold,
    expected.avg_order_line_value as expected_avg_order_line_value,
    actual.avg_order_line_value as actual_avg_order_line_value,
    expected.discounted_revenue as expected_discounted_revenue,
    actual.discounted_revenue as actual_discounted_revenue
from (
    select
        cast(order_date as date) as order_date,
        count_big(*) as source_line_count,
        count(distinct sales_order_id) as total_orders,
        count(distinct customer_id) as unique_customers,
        sum(order_qty) as total_items_sold,
        count(distinct case when order_channel = 'Online' then sales_order_id end) as online_orders,
        count(distinct case when order_channel = 'Offline' then sales_order_id end) as offline_orders,
        sum(line_total) as total_revenue,
        sum(line_total) / nullif(count(line_total), 0) as avg_order_line_value,
        sum(case when has_discount = 1 then line_total else 0 end) as discounted_revenue
    from {{ ref('slvr_sales_orders') }}
    group by cast(order_date as date)
) as expected
full outer join (
    select *, 1 as actual_present
    from {{ ref('gld_sales_summary') }}
) as actual on actual.order_date = expected.order_date
where expected.source_line_count is null
    or actual.actual_present is null
    or exists (
        select
            expected.total_orders, expected.online_orders, expected.offline_orders,
            expected.unique_customers, expected.total_items_sold
        except
        select
            actual.total_orders, actual.online_orders, actual.offline_orders,
            actual.unique_customers, actual.total_items_sold
    )
    or actual.online_orders + actual.offline_orders <> actual.total_orders
    or (expected.total_revenue is null and actual.total_revenue is not null)
    or (expected.total_revenue is not null and actual.total_revenue is null)
    or abs(expected.total_revenue - actual.total_revenue) > 0.01
    or (expected.avg_order_line_value is null and actual.avg_order_line_value is not null)
    or (expected.avg_order_line_value is not null and actual.avg_order_line_value is null)
    or abs(expected.avg_order_line_value - actual.avg_order_line_value) > 0.01
    or (expected.discounted_revenue is null and actual.discounted_revenue is not null)
    or (expected.discounted_revenue is not null and actual.discounted_revenue is null)
    or abs(expected.discounted_revenue - actual.discounted_revenue) > 0.01
