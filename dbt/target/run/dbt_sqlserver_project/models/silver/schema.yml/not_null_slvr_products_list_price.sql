
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_3732727e46bc8d1c9e77fc769e7633bd]
   as 
    
    



select list_price
from "AdventureWorks2014"."silver"."slvr_products"
where list_price is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_3732727e46bc8d1c9e77fc769e7633bd]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_3732727e46bc8d1c9e77fc769e7633bd]
  ;')