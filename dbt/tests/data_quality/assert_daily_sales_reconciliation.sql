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
    actual.total_revenue as actual_total_revenue
from (
    select
        cast(order_date as date) as order_date,
        count_big(*) as source_line_count,
        count(distinct sales_order_id) as total_orders,
        count(distinct case when order_channel = 'Online' then sales_order_id end) as online_orders,
        count(distinct case when order_channel = 'Offline' then sales_order_id end) as offline_orders,
        sum(line_total) as total_revenue
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
        select expected.total_orders, expected.online_orders, expected.offline_orders
        except
        select actual.total_orders, actual.online_orders, actual.offline_orders
    )
    or actual.online_orders + actual.offline_orders <> actual.total_orders
    or (expected.total_revenue is null and actual.total_revenue is not null)
    or (expected.total_revenue is not null and actual.total_revenue is null)
    or abs(expected.total_revenue - actual.total_revenue) > 0.01
