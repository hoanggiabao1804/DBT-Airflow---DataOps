
  
    USE [AdventureWorks2014];
    USE [AdventureWorks2014];
    
    

    

    
    USE [AdventureWorks2014];
    EXEC('
        create view "silver"."slvr_sales_orders__dbt_tmp__dbt_tmp_vw" as 

with bronze_sales as (
    select * from "AdventureWorks2014"."bronze"."brnz_sales_orders"
),

cleaned as (
    select
        sales_order_id,
        order_detail_id,
        order_date,
        due_date,
        ship_date,
        status,
        case 
            when online_order_flag = 1 then ''Online''
            else ''Offline''
        end as order_channel,
        sales_order_number,
        purchase_order_number,
        customer_id,
        sales_person_id,
        territory_id,
        product_id,
        order_qty,
        unit_price,
        unit_price_discount,
        line_total,
        -- Calculated fields
        unit_price * order_qty as gross_amount,
        line_total / nullif(order_qty, 0) as effective_unit_price,
        case 
            when unit_price_discount > 0 then 1
            else 0
        end as has_discount
    from bronze_sales
    where order_qty > 0
        and unit_price >= 0
)

select * from cleaned;
    ')

EXEC('
            SELECT * INTO "AdventureWorks2014"."silver"."slvr_sales_orders__dbt_tmp" FROM "AdventureWorks2014"."silver"."slvr_sales_orders__dbt_tmp__dbt_tmp_vw" 
    OPTION (LABEL = ''dbt-sqlserver'');

        ')

    
    EXEC('DROP VIEW IF EXISTS silver.slvr_sales_orders__dbt_tmp__dbt_tmp_vw')



    
    use [AdventureWorks2014];
    if EXISTS (
        SELECT *
        FROM sys.indexes with (nolock)
        WHERE name = 'silver_slvr_sales_orders__dbt_tmp_cci'
        AND object_id=object_id('silver_slvr_sales_orders__dbt_tmp')
    )
    DROP index "silver"."slvr_sales_orders__dbt_tmp".silver_slvr_sales_orders__dbt_tmp_cci
    CREATE CLUSTERED COLUMNSTORE INDEX silver_slvr_sales_orders__dbt_tmp_cci
    ON "silver"."slvr_sales_orders__dbt_tmp"

   


  