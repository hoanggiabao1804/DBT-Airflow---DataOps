
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_a5fdc387d46671207c7aad6c3cd2e325]
   as 
    
    

select
    order_date as unique_field,
    count(*) as n_records

from "AdventureWorks2014"."gold"."gld_sales_summary"
where order_date is not null
group by order_date
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

    [dbt_test__audit.testview_a5fdc387d46671207c7aad6c3cd2e325]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_a5fdc387d46671207c7aad6c3cd2e325]
  ;')