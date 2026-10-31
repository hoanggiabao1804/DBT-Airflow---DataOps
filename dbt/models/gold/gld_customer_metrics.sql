{{
    config(
        materialized='table'
    )
}}

with customers as (
    select * from {{ ref('slvr_customers') }}
),

sales as (
    select * from {{ ref('slvr_sales_orders') }}
),

customer_sales as (
    select
        c.customer_id,
        c.full_name,
        c.territory_id,
        count(distinct s.sales_order_id) as total_orders,
        sum(s.line_total) as total_revenue,
        avg(s.line_total) as avg_order_value,
        sum(s.order_qty) as total_items_purchased,
        min(s.order_date) as first_order_date,
        max(s.order_date) as last_order_date,
        sum(case when s.has_discount = 1 then 1 else 0 end) as orders_with_discount
    from customers c
    left join sales s
        on c.customer_id = s.customer_id
    group by c.customer_id, c.full_name, c.territory_id
)

select * from customer_sales
