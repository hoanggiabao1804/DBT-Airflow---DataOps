{{
    config(
        materialized='table'
    )
}}

with bronze_products as (
    select * from {{ ref('brnz_products') }}
),

cleaned as (
    select
        ProductID as product_id,
        ProductName as product_name,
        ProductNumber as product_number,
        coalesce(Color, 'N/A') as color,
        StandardCost as standard_cost,
        ListPrice as list_price,
        coalesce(Size, 'N/A') as size,
        coalesce(Weight, 0) as weight,
        ProductLine as product_line,
        Class as class,
        Style as style,
        ProductSubcategoryID as subcategory_id,
        coalesce(SubcategoryName, 'Uncategorized') as subcategory_name,
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

select * from cleaned
