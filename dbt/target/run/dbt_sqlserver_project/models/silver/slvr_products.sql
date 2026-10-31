
  
    USE [AdventureWorks2014];
    USE [AdventureWorks2014];
    
    

    

    
    USE [AdventureWorks2014];
    EXEC('
        create view "silver"."slvr_products__dbt_tmp__dbt_tmp_vw" as 

with bronze_products as (
    select * from "AdventureWorks2014"."bronze"."brnz_products"
),

cleaned as (
    select
        ProductID as product_id,
        ProductName as product_name,
        ProductNumber as product_number,
        coalesce(Color, ''N/A'') as color,
        StandardCost as standard_cost,
        ListPrice as list_price,
        coalesce(Size, ''N/A'') as size,
        coalesce(Weight, 0) as weight,
        ProductLine as product_line,
        Class as class,
        Style as style,
        ProductSubcategoryID as subcategory_id,
        coalesce(SubcategoryName, ''Uncategorized'') as subcategory_name,
        ProductCategoryID as category_id,
        SellStartDate as sell_start_date,
        SellEndDate as sell_end_date,
        case 
            when DiscontinuedDate is not null then 1
            else 0
        end as is_discontinued,
        last_modified_date
    from bronze_products
)

select * from cleaned;
    ')

EXEC('
            SELECT * INTO "AdventureWorks2014"."silver"."slvr_products__dbt_tmp" FROM "AdventureWorks2014"."silver"."slvr_products__dbt_tmp__dbt_tmp_vw" 
    OPTION (LABEL = ''dbt-sqlserver'');

        ')

    
    EXEC('DROP VIEW IF EXISTS silver.slvr_products__dbt_tmp__dbt_tmp_vw')



    
    use [AdventureWorks2014];
    if EXISTS (
        SELECT *
        FROM sys.indexes with (nolock)
        WHERE name = 'silver_slvr_products__dbt_tmp_cci'
        AND object_id=object_id('silver_slvr_products__dbt_tmp')
    )
    DROP index "silver"."slvr_products__dbt_tmp".silver_slvr_products__dbt_tmp_cci
    CREATE CLUSTERED COLUMNSTORE INDEX silver_slvr_products__dbt_tmp_cci
    ON "silver"."slvr_products__dbt_tmp"

   


  