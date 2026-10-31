
    
    

select
    customer_id as unique_field,
    count(*) as n_records

from "AdventureWorks2014"."silver"."slvr_customers"
where customer_id is not null
group by customer_id
having count(*) > 1


