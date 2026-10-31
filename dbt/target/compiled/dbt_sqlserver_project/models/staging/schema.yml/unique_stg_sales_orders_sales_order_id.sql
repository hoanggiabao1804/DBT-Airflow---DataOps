
    
    

select
    sales_order_id as unique_field,
    count(*) as n_records

from "AdventureWorks2014"."dbo"."stg_sales_orders"
where sales_order_id is not null
group by sales_order_id
having count(*) > 1


