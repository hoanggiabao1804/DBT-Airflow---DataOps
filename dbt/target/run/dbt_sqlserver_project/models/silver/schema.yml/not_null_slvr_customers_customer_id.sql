
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_a3e2f658e14c8defedfb0ef02c0f35ee]
   as 
    
    



select customer_id
from "AdventureWorks2014"."silver"."slvr_customers"
where customer_id is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_a3e2f658e14c8defedfb0ef02c0f35ee]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_a3e2f658e14c8defedfb0ef02c0f35ee]
  ;')