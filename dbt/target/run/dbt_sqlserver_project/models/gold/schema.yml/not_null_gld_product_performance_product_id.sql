
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_d9e4a60ce3302f950b7141c625f457af]
   as 
    
    



select product_id
from "AdventureWorks2014"."gold"."gld_product_performance"
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

    [dbt_test__audit.testview_d9e4a60ce3302f950b7141c625f457af]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_d9e4a60ce3302f950b7141c625f457af]
  ;')