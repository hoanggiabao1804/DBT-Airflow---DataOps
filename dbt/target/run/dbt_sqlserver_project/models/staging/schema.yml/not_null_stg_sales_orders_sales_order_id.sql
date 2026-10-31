
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_cb4bee4a18e6fbf1edbc534d03222f47]
   as 
    
    



select sales_order_id
from "AdventureWorks2014"."dbo"."stg_sales_orders"
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

    [dbt_test__audit.testview_cb4bee4a18e6fbf1edbc534d03222f47]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_cb4bee4a18e6fbf1edbc534d03222f47]
  ;')