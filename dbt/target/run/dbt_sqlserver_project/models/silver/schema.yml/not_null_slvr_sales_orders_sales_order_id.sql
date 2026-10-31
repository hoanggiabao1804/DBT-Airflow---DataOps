
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_0186f03c9f651b264572095d2bf1a779]
   as 
    
    



select sales_order_id
from "AdventureWorks2014"."silver"."slvr_sales_orders"
where sales_order_id is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_0186f03c9f651b264572095d2bf1a779]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_0186f03c9f651b264572095d2bf1a779]
  ;')