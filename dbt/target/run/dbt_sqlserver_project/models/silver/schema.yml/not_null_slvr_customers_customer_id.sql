
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_4850e41a05a4361004983135ba6401ea]
   as 
    
    



select customer_id
from "AdventureWorks2014"."silver"."slvr_customers"
where customer_id is null


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_4850e41a05a4361004983135ba6401ea]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_4850e41a05a4361004983135ba6401ea]
  ;')