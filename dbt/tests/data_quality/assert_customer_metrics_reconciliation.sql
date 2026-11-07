{{ config(tags=['data_quality', 'reconciliation']) }}

-- Aggregate at order grain first: AVG(order revenue) is independent of the
-- number of lines in an order; one discounted line marks the whole order.
-- The customer dimension anchors the result, including customers with no sales:
-- their order counts are zero and revenue/AOV remain NULL.
select
    coalesce(expected.customer_id, actual.customer_id) as customer_id,
    expected.total_orders as expected_total_orders,
    actual.total_orders as actual_total_orders,
    expected.orders_with_discount as expected_discounted_orders,
    actual.orders_with_discount as actual_discounted_orders,
    expected.total_revenue as expected_total_revenue,
    actual.total_revenue as actual_total_revenue,
    expected.avg_order_value as expected_avg_order_value,
    actual.avg_order_value as actual_avg_order_value
from (
    select
        customers.customer_id,
        1 as expected_present,
        count(orders.sales_order_id) as total_orders,
        sum(orders.order_revenue) as total_revenue,
        avg(orders.order_revenue) as avg_order_value,
        count(case when orders.discounted = 1 then orders.sales_order_id end) as orders_with_discount
    from {{ ref('slvr_customers') }} as customers
    left join (
        select
            customer_id,
            sales_order_id,
            sum(line_total) as order_revenue,
            max(has_discount) as discounted
        from {{ ref('slvr_sales_orders') }}
        group by customer_id, sales_order_id
    ) as orders on orders.customer_id = customers.customer_id
    group by customers.customer_id
) as expected
full outer join (
    select *, 1 as actual_present
    from {{ ref('gld_customer_metrics') }}
) as actual on actual.customer_id = expected.customer_id
where expected.expected_present is null
    or actual.actual_present is null
    or exists (
        select expected.total_orders, expected.orders_with_discount
        except
        select actual.total_orders, actual.orders_with_discount
    )
    or (expected.total_revenue is null and actual.total_revenue is not null)
    or (expected.total_revenue is not null and actual.total_revenue is null)
    or abs(expected.total_revenue - actual.total_revenue) > 0.01
    or (expected.avg_order_value is null and actual.avg_order_value is not null)
    or (expected.avg_order_value is not null and actual.avg_order_value is null)
    or abs(expected.avg_order_value - actual.avg_order_value) > 0.01
