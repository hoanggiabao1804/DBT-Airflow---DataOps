

with source as (
    select * from "AdventureWorks2014"."Sales"."Customer"
),

person as (
    select * from "AdventureWorks2014"."Person"."Person"
),

staged as (
    select
        c.CustomerID,
        p.FirstName,
        p.LastName,
        p.EmailPromotion,
        c.StoreID,
        c.TerritoryID,
        c.ModifiedDate as last_modified_date
    from source c
    left join person p
        on c.PersonID = p.BusinessEntityID
)

select * from staged