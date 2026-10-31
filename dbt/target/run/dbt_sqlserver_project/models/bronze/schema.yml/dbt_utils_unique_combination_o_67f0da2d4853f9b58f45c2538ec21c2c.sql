
  
  

  
  USE [AdventureWorks2014];
  EXEC('create view 

    [dbt_test__audit.testview_e469becceeffdd2d421a7c040b481e1c]
   as 





with validation_errors as (

    select
        sales_order_id, order_detail_id
    from "AdventureWorks2014"."bronze"."brnz_sales_orders"
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

    [dbt_test__audit.testview_e469becceeffdd2d421a7c040b481e1c]
  
  ) dbt_internal_test;

  USE [AdventureWorks2014];
  EXEC('drop view 

    [dbt_test__audit.testview_e469becceeffdd2d421a7c040b481e1c]
  ;')