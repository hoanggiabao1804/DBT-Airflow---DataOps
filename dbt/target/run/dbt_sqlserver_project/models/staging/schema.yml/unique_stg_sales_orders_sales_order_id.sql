
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_31e5b33cbc29e025b0d4475ea0062398]
   as 
    
    

select
    sales_order_id as unique_field,
    count(*) as n_records

from "AdventureWorks2014"."dbo"."stg_sales_orders"
where sales_order_id is not null
group by sales_order_id
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

    [dbt_test__audit.testview_31e5b33cbc29e025b0d4475ea0062398]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_31e5b33cbc29e025b0d4475ea0062398]
  ;')