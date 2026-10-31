USE [AdventureWorks2014];
    
    

    

    
    USE [AdventureWorks2014];
    EXEC('
        create view "bronze"."brnz_products__dbt_tmp" as with product as (
    select * from "AdventureWorks2014"."Production"."Product"
),

product_subcategory as (
    select * from "AdventureWorks2014"."Production"."ProductSubcategory"
),

staged as (
    select
        p.ProductID,
        p.Name as ProductName,
        p.ProductNumber,
        p.MakeFlag,
        p.FinishedGoodsFlag,
        p.Color,
        p.SafetyStockLevel,
        p.ReorderPoint,
        p.StandardCost,
        p.ListPrice,
        p.Size,
        p.SizeUnitMeasureCode,
        p.WeightUnitMeasureCode,
        p.Weight,
        p.DaysToManufacture,
        p.ProductLine,
        p.Class,
        p.Style,
        p.ProductSubcategoryID,
        p.ProductModelID,
        p.SellStartDate,
        p.SellEndDate,
        p.DiscontinuedDate,
        ps.Name as SubcategoryName,
        ps.ProductCategoryID,
        p.ModifiedDate as last_modified_date
    from product p
    left join product_subcategory ps
        on p.ProductSubcategoryID = ps.ProductSubcategoryID
)

select * from staged;
    ')

