{{ config(tags=['data_quality', 'reconciliation']) }}

-- Silver product cleaning must preserve every Bronze product key, including
-- unsold products. Existing not_null/unique tests enforce the dimension grain.
select
    coalesce(bronze.ProductID, silver.product_id) as product_id,
    bronze.bronze_present,
    silver.silver_present
from (
    select ProductID, 1 as bronze_present
    from {{ ref('brnz_products') }}
) as bronze
full outer join (
    select product_id, 1 as silver_present
    from {{ ref('slvr_products') }}
) as silver on silver.product_id = bronze.ProductID
where bronze.bronze_present is null
    or silver.silver_present is null
