
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_0e38119346aebc0e50b9ba01b95ec46d]
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

    [dbt_test__audit.testview_0e38119346aebc0e50b9ba01b95ec46d]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_0e38119346aebc0e50b9ba01b95ec46d]
  ;')