{{ config(tags=['data_quality', 'reconciliation']) }}

-- Silver must preserve exactly the eligible Bronze lines, not the unfiltered
-- Bronze row count. Keys/duplicates/required NULLs have separate schema tests.
-- EXCEPT compares forwarded values NULL-safely, including nullable ship_date.
select
    coalesce(expected.sales_order_id, actual.sales_order_id) as sales_order_id,
    coalesce(expected.order_detail_id, actual.order_detail_id) as order_detail_id,
    expected.expected_present,
    actual.actual_present,
    expected.line_total as expected_line_total,
    actual.line_total as actual_line_total,
    expected.order_qty as expected_order_qty,
    actual.order_qty as actual_order_qty
from (
    select *, 1 as expected_present
    from {{ ref('brnz_sales_orders') }}
    where order_qty > 0 and unit_price >= 0
) as expected
full outer join (
    select *, 1 as actual_present
    from {{ ref('slvr_sales_orders') }}
) as actual
    on actual.sales_order_id = expected.sales_order_id
    and actual.order_detail_id = expected.order_detail_id
where expected.expected_present is null
    or actual.actual_present is null
    or exists (
        select
            expected.customer_id, expected.product_id,
            expected.order_date, expected.due_date, expected.ship_date,
            expected.order_qty, expected.unit_price,
            expected.unit_price_discount, expected.line_total,
            case when expected.online_order_flag = 1 then 'Online' else 'Offline' end,
            case when expected.unit_price_discount > 0 then 1 else 0 end
        except
        select
            actual.customer_id, actual.product_id,
            actual.order_date, actual.due_date, actual.ship_date,
            actual.order_qty, actual.unit_price,
            actual.unit_price_discount, actual.line_total,
            actual.order_channel, actual.has_discount
    )
    or actual.gross_amount is null
    or abs(actual.gross_amount - expected.unit_price * expected.order_qty) > 0.01
    or (expected.line_total is null and actual.effective_unit_price is not null)
    or (expected.line_total is not null and actual.effective_unit_price is null)
    or abs(actual.effective_unit_price - expected.line_total / nullif(expected.order_qty, 0)) > 0.0001
