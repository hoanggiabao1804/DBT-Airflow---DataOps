{{
    config(
        materialized='table'
    )
}}

with sales as (
    select * from {{ ref('slvr_sales_orders') }}
),

daily_summary as (
    select
        cast(order_date as date) as order_date,
        count(distinct sales_order_id) as total_orders,
        count(distinct customer_id) as unique_customers,
        sum(order_qty) as total_items_sold,
        sum(line_total) as total_revenue,
        avg(line_total) as avg_order_line_value,
        -- An order can contain several lines, including in the same channel.
        count(distinct case when order_channel = 'Online' then sales_order_id end) as online_orders,
        count(distinct case when order_channel = 'Offline' then sales_order_id end) as offline_orders,
        sum(case when has_discount = 1 then line_total else 0 end) as discounted_revenue
    from sales
    group by cast(order_date as date)
)

select * from daily_summary
