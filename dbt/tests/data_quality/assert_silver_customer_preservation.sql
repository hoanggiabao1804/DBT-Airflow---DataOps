{{ config(tags=['data_quality', 'reconciliation']) }}

-- Silver customer cleaning must preserve every Bronze customer key. Existing
-- not_null/unique tests enforce grain; this symmetric check also finds lost keys.
select
    coalesce(bronze.CustomerID, silver.customer_id) as customer_id,
    bronze.bronze_present,
    silver.silver_present
from (
    select CustomerID, 1 as bronze_present
    from {{ ref('brnz_customers') }}
) as bronze
full outer join (
    select customer_id, 1 as silver_present
    from {{ ref('slvr_customers') }}
) as silver on silver.customer_id = bronze.CustomerID
where bronze.bronze_present is null
    or silver.silver_present is null
