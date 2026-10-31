
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_56f3e5f9429c339591a62dde4bf0ef7e]
   as 





with validation_errors as (

    select
        sales_order_id, order_detail_id
    from "AdventureWorks2014"."dbo"."stg_sales_orders"
    group by sales_order_id, order_detail_id
    having count(*) > 1

)

select *
from validation_errors


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_56f3e5f9429c339591a62dde4bf0ef7e]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_56f3e5f9429c339591a62dde4bf0ef7e]
  ;')