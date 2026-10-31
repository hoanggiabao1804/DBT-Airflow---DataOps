
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_a850aad6cc7eb3d6573028804fd3d337]
   as 
    
    



select line_total
from "AdventureWorks2014"."silver"."slvr_sales_orders"
where line_total is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_a850aad6cc7eb3d6573028804fd3d337]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_a850aad6cc7eb3d6573028804fd3d337]
  ;')