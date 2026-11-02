with sales_order_header as (
    select
        SalesOrderID as sales_order_id,
        OrderDate as order_date,
        DueDate as due_date,
        ShipDate as ship_date,
        Status as status,
        OnlineOrderFlag as online_order_flag,
        SalesOrderNumber as sales_order_number,
        PurchaseOrderNumber as purchase_order_number,
        CustomerID as customer_id,
        SalesPersonID as sales_person_id,
        TerritoryID as territory_id
    from {{ source('adventureworks', 'SalesOrderHeader') }}
),

sales_order_detail as (
    select
        SalesOrderDetailID as order_detail_id,
        SalesOrderID as sales_order_id,
        ProductID as product_id,
        OrderQty as order_qty,
        UnitPrice as unit_price,
        UnitPriceDiscount as unit_price_discount,
        LineTotal as line_total
    from {{ source('adventureworks', 'SalesOrderDetail') }}
)

select
    h.sales_order_id,
    h.order_date,
    h.due_date,
    h.ship_date,
    h.status,
    h.online_order_flag,
    h.sales_order_number,
    h.purchase_order_number,
    h.customer_id,
    h.sales_person_id,
    h.territory_id,
    d.order_detail_id,
    d.product_id,
    d.order_qty,
    d.unit_price,
    d.unit_price_discount,
    d.line_total
from sales_order_header h
left join sales_order_detail d
    on h.sales_order_id = d.sales_order_id
