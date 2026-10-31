USE [AdventureWorks2014];
    
    

    

    
    USE [AdventureWorks2014];
    EXEC('
        create view "dbo"."stg_example__dbt_tmp" as 

with source_data as (
    select * from "AdventureWorks2014"."Sales"."Customer"
),

transformed as (
    select
        CustomerID as id,
        AccountNumber as name,
        ModifiedDate as created_at,
        ModifiedDate as updated_at
    from source_data
)

select * from transformed;
    ')

