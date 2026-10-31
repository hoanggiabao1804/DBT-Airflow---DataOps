
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_018d59e2b6d8a7554ffac2e7fb67a575]
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

    [dbt_test__audit.testview_018d59e2b6d8a7554ffac2e7fb67a575]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_018d59e2b6d8a7554ffac2e7fb67a575]
  ;')