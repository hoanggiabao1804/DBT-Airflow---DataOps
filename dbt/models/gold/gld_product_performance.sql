{{
    config(
        materialized='table'
    )
}}

with products as (
    select * from {{ ref('slvr_products') }}
),

sales as (
    select * from {{ ref('slvr_sales_orders') }}
),

product_sales as (
    select
        p.product_id,
        p.product_name,
        p.subcategory_name,
        p.color,
        p.list_price,
        p.standard_cost,
        count(distinct s.sales_order_id) as total_orders,
        sum(s.order_qty) as total_quantity_sold,
        sum(s.line_total) as total_revenue,
        avg(s.unit_price) as avg_selling_price,
        sum(s.line_total) - (sum(s.order_qty) * p.standard_cost) as total_profit,
        case 
            when sum(s.order_qty) > 0 then 
                (sum(s.line_total) - (sum(s.order_qty) * p.standard_cost)) / sum(s.line_total) * 100
            else 0
        end as profit_margin_pct
    from products p
    left join sales s
        on p.product_id = s.product_id
    group by 
        p.product_id, 
        p.product_name, 
        p.subcategory_name, 
        p.color, 
        p.list_price, 
        p.standard_cost
)

select * from product_sales
