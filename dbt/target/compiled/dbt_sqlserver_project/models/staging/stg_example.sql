

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

select * from transformed