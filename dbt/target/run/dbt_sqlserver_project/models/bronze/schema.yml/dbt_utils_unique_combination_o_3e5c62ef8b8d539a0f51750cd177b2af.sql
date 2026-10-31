
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_3e272a76c43249f01e514d46632cb8a0]
   as 





with validation_errors as (

    select
        sales_order_id, order_detail_id
    from "AdventureWorks2014"."dbo"."stg_sales_orders"
    group by sales_order_id, order_detail_id
    having count(*) > 1

)

select *
from validation_errors


;')
  select
    count(*) as failures,
    case when count(*) != 0
      then 'true' else 'false' end as should_warn,
    case when count(*) != 0
      then 'true' else 'false' end as should_error
  from (
    select  * from 

    [dbt_test__audit.testview_3e272a76c43249f01e514d46632cb8a0]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_3e272a76c43249f01e514d46632cb8a0]
  ;')