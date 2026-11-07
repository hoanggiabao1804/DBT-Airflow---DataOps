{{ config(tags=['data_quality', 'reconciliation']) }}

-- Reconcile per product, never SUM(total_orders) across products: one order can
-- contain several products. Profit uses the current dimension standard_cost.
-- No sales: counts=0, SUM metrics=NULL, margin=0 (existing contract).
-- Sales with zero revenue: margin=NULL because the percentage is undefined.
select
    coalesce(expected.product_id, actual.product_id) as product_id,
    expected.total_orders as expected_total_orders,
    actual.total_orders as actual_total_orders,
    expected.total_quantity_sold as expected_quantity,
    actual.total_quantity_sold as actual_quantity,
    expected.total_revenue as expected_revenue,
    actual.total_revenue as actual_revenue,
    expected.total_profit as expected_profit,
    actual.total_profit as actual_profit,
    expected.profit_margin_pct as expected_margin,
    actual.profit_margin_pct as actual_margin
from (
    select
        products.product_id,
        1 as expected_present,
        coalesce(sales.total_orders, 0) as total_orders,
        sales.total_quantity_sold,
        sales.total_revenue,
        sales.total_revenue - sales.total_quantity_sold * products.standard_cost as total_profit,
        case
            when sales.total_quantity_sold > 0 then
                (sales.total_revenue - sales.total_quantity_sold * products.standard_cost)
                    / nullif(sales.total_revenue, 0) * 100
            else 0
        end as profit_margin_pct
    from {{ ref('slvr_products') }} as products
    left join (
        select
            product_id,
            count(distinct sales_order_id) as total_orders,
            sum(order_qty) as total_quantity_sold,
            sum(line_total) as total_revenue
        from {{ ref('slvr_sales_orders') }}
        group by product_id
    ) as sales on sales.product_id = products.product_id
) as expected
full outer join (
    select *, 1 as actual_present
    from {{ ref('gld_product_performance') }}
) as actual on actual.product_id = expected.product_id
where expected.expected_present is null
    or actual.actual_present is null
    or exists (
        select expected.total_orders, expected.total_quantity_sold
        except
        select actual.total_orders, actual.total_quantity_sold
    )
    or (expected.total_revenue is null and actual.total_revenue is not null)
    or (expected.total_revenue is not null and actual.total_revenue is null)
    or abs(expected.total_revenue - actual.total_revenue) > 0.01
    or (expected.total_profit is null and actual.total_profit is not null)
    or (expected.total_profit is not null and actual.total_profit is null)
    or abs(expected.total_profit - actual.total_profit) > 0.01
    or (expected.profit_margin_pct is null and actual.profit_margin_pct is not null)
    or (expected.profit_margin_pct is not null and actual.profit_margin_pct is null)
    or abs(expected.profit_margin_pct - actual.profit_margin_pct) > 0.0001
