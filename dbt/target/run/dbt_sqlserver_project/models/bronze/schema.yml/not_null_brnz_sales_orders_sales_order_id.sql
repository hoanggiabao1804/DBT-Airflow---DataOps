
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_ad24aae890529dcfca084c0d3060dd68]
   as 
    
    



select sales_order_id
from "AdventureWorks2014"."bronze"."brnz_sales_orders"
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

    [dbt_test__audit.testview_ad24aae890529dcfca084c0d3060dd68]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_ad24aae890529dcfca084c0d3060dd68]
  ;')