
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_f1c217333ca83d8eb8541a65d5cb51b5]
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

    [dbt_test__audit.testview_f1c217333ca83d8eb8541a65d5cb51b5]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_f1c217333ca83d8eb8541a65d5cb51b5]
  ;')