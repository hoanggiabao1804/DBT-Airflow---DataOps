
  
    USE [AdventureWorks2014];
    USE [AdventureWorks2014];
    
    

    

    
    USE [AdventureWorks2014];
    EXEC('
        create view "silver"."slvr_customers__dbt_tmp__dbt_tmp_vw" as 

with bronze_customers as (
    select * from "AdventureWorks2014"."bronze"."brnz_customers"
),

cleaned as (
    select
        CustomerID as customer_id,
        coalesce(FirstName, ''Unknown'') as first_name,
        coalesce(LastName, ''Unknown'') as last_name,
        concat(coalesce(FirstName, ''Unknown''), '' '', coalesce(LastName, ''Unknown'')) as full_name,
        EmailPromotion as email_promotion,
        StoreID as store_id,
        TerritoryID as territory_id,
        last_modified_date
    from bronze_customers
)

select * from cleaned;
    ')

EXEC('
            SELECT * INTO "AdventureWorks2014"."silver"."slvr_customers__dbt_tmp" FROM "AdventureWorks2014"."silver"."slvr_customers__dbt_tmp__dbt_tmp_vw" 
    OPTION (LABEL = ''dbt-sqlserver'');

        ')

    
    EXEC('DROP VIEW IF EXISTS silver.slvr_customers__dbt_tmp__dbt_tmp_vw')



    
    use [AdventureWorks2014];
    if EXISTS (
        SELECT *
        FROM sys.indexes with (nolock)
        WHERE name = 'silver_slvr_customers__dbt_tmp_cci'
        AND object_id=object_id('silver_slvr_customers__dbt_tmp')
    )
    DROP index "silver"."slvr_customers__dbt_tmp".silver_slvr_customers__dbt_tmp_cci
    CREATE CLUSTERED COLUMNSTORE INDEX silver_slvr_customers__dbt_tmp_cci
    ON "silver"."slvr_customers__dbt_tmp"

   


  