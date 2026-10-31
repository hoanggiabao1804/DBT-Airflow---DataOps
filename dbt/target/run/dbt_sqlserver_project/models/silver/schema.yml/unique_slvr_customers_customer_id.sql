
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_b4eb90b800ef96a9947a5bb360fb26a3]
   as 
    
    

select
    customer_id as unique_field,
    count(*) as n_records

from "AdventureWorks2014"."silver"."slvr_customers"
where customer_id is not null
group by customer_id
having count(*) > 1


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_b4eb90b800ef96a9947a5bb360fb26a3]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_b4eb90b800ef96a9947a5bb360fb26a3]
  ;')