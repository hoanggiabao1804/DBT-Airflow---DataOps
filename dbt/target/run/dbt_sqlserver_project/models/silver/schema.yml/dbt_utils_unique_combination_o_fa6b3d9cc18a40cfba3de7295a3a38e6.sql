
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_74cb0cbcb4ecbb2e887b5b87b7ca0705]
   as 





with validation_errors as (

    select
        sales_order_id, order_detail_id
    from "AdventureWorks2014"."silver"."slvr_sales_orders"
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

    [dbt_test__audit.testview_74cb0cbcb4ecbb2e887b5b87b7ca0705]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_74cb0cbcb4ecbb2e887b5b87b7ca0705]
  ;')