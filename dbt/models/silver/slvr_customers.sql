{{
    config(
        materialized='table'
    )
}}

with bronze_customers as (
    select * from {{ ref('brnz_customers') }}
),

cleaned as (
    select
        CustomerID as customer_id,
        coalesce(FirstName, 'Unknown') as first_name,
        coalesce(LastName, 'Unknown') as last_name,
        concat(coalesce(FirstName, 'Unknown'), ' ', coalesce(LastName, 'Unknown')) as full_name,
        EmailPromotion as email_promotion,
        StoreID as store_id,
        TerritoryID as territory_id,
        last_modified_date
    from bronze_customers
)

select * from cleaned
