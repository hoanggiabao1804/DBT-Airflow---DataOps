
  
    USE [AdventureWorks2014];
    USE [AdventureWorks2014];
    
    

    

    
    USE [AdventureWorks2014];
    EXEC('
        create view "gold"."gld_customer_metrics__dbt_tmp__dbt_tmp_vw" as 

with customers as (
    select * from "AdventureWorks2014"."silver"."slvr_customers"
),

sales as (
    select * from "AdventureWorks2014"."silver"."slvr_sales_orders"
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

select * from customer_sales;
    ')

EXEC('
            SELECT * INTO "AdventureWorks2014"."gold"."gld_customer_metrics__dbt_tmp" FROM "AdventureWorks2014"."gold"."gld_customer_metrics__dbt_tmp__dbt_tmp_vw" 
    OPTION (LABEL = ''dbt-sqlserver'');

        ')

    
    EXEC('DROP VIEW IF EXISTS gold.gld_customer_metrics__dbt_tmp__dbt_tmp_vw')



    
    use [AdventureWorks2014];
    if EXISTS (
        SELECT *
        FROM sys.indexes with (nolock)
        WHERE name = 'gold_gld_customer_metrics__dbt_tmp_cci'
        AND object_id=object_id('gold_gld_customer_metrics__dbt_tmp')
    )
    DROP index "gold"."gld_customer_metrics__dbt_tmp".gold_gld_customer_metrics__dbt_tmp_cci
    CREATE CLUSTERED COLUMNSTORE INDEX gold_gld_customer_metrics__dbt_tmp_cci
    ON "gold"."gld_customer_metrics__dbt_tmp"

   


  