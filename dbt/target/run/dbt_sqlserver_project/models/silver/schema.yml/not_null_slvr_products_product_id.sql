
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_41d157483de22e2d29ce4fad81cc51a6]
   as 
    
    



select product_id
from "AdventureWorks2014"."silver"."slvr_products"
where product_id is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_41d157483de22e2d29ce4fad81cc51a6]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_41d157483de22e2d29ce4fad81cc51a6]
  ;')