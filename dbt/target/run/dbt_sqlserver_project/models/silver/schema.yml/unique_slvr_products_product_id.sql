
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_35a889afec725fb6c2abf011b7d53cbd]
   as 
    
    

select
    product_id as unique_field,
    count(*) as n_records

from "AdventureWorks2014"."silver"."slvr_products"
where product_id is not null
group by product_id
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

    [dbt_test__audit.testview_35a889afec725fb6c2abf011b7d53cbd]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_35a889afec725fb6c2abf011b7d53cbd]
  ;')