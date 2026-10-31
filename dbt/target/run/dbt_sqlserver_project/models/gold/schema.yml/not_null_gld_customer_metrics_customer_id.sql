
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_d7ab67fdeb2572270b593a1407b0cfad]
   as 
    
    



select customer_id
from "AdventureWorks2014"."gold"."gld_customer_metrics"
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

    [dbt_test__audit.testview_d7ab67fdeb2572270b593a1407b0cfad]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_d7ab67fdeb2572270b593a1407b0cfad]
  ;')