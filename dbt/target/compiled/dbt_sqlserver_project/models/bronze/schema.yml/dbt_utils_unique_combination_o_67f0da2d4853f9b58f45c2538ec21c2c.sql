





with validation_errors as (

    select
        sales_order_id, order_detail_id
    from "AdventureWorks2014"."bronze"."brnz_sales_orders"
    group by sales_order_id, order_detail_id
    having count(*) > 1

)

select *
from validation_errors


