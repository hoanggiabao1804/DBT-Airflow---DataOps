
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_7029fdc4aea731d1c0ab364c86f149f2]
   as 
    
    



select order_detail_id
from "AdventureWorks2014"."bronze"."brnz_sales_orders"
where order_detail_id is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_7029fdc4aea731d1c0ab364c86f149f2]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_7029fdc4aea731d1c0ab364c86f149f2]
  ;')