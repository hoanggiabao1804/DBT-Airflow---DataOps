
    
    

select
    order_date as unique_field,
    count(*) as n_records

from "AdventureWorks2014"."gold"."gld_sales_summary"
where order_date is not null
group by order_date
having count(*) > 1


