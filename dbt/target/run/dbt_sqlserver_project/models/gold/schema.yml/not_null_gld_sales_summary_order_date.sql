
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_a2318f38f44a6937cbf2862348c845d2]
   as 
    
    



select order_date
from "AdventureWorks2014"."gold"."gld_sales_summary"
where order_date is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_a2318f38f44a6937cbf2862348c845d2]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_a2318f38f44a6937cbf2862348c845d2]
  ;')