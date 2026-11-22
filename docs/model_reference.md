# Giao diện dữ liệu và dbt models

Project này **không cung cấp HTTP API**. Giao diện được dùng bởi người phân
tích và các job khác là các relations trong SQL Server và dbt docs sinh từ
schema YAML. Target `dev` đặt database `AdventureWorks2014`; Bronze là views,
Silver/Gold là tables theo [`dbt_project.yml`](../dbt/dbt_project.yml).
Tên schema có thể khác nếu target khác cấu hình.

## Nguồn và lineage

Sáu nguồn đang dùng: `Sales.Customer`, `Person.Person`,
`Production.Product`, `Production.ProductSubcategory`,
`Sales.SalesOrderHeader`, `Sales.SalesOrderDetail`. Các khai báo `raw` trong
[`models/sources.yml`](../dbt/models/sources.yml) là di sản không được models
hiện tại tham chiếu. Xem [sơ đồ](architecture.md) và
[lineage chi tiết](tuan_data_lineage.md) để truy theo từng cạnh `source()`/
`ref()`; model SQL là định nghĩa thực thi cuối cùng.

| Relation dev | Grain / khóa | Nguồn trực tiếp | Vai trò và cột chính |
| --- | --- | --- | --- |
| [`bronze.brnz_customers`](../dbt/models/bronze/brnz_customers.sql) | 1 dòng/`CustomerID` | `Sales.Customer` + `Person.Person` | LEFT JOIN để giữ cả khách thiếu Person; tên và `EmailPromotion` có thể NULL; `last_modified_date` lấy Customer. |
| [`bronze.brnz_example`](../dbt/models/bronze/brnz_example.sql) | 1 dòng/`id` | `Sales.Customer` | Ví dụ minh họa; `name` là `AccountNumber`, không có downstream. |
| [`bronze.brnz_products`](../dbt/models/bronze/brnz_products.sql) | 1 dòng/`ProductID` | `Production.Product` + `ProductSubcategory` | Giữ sản phẩm thiếu subcategory; có `ProductName`, `StandardCost`, `ListPrice`, `last_modified_date`. |
| [`bronze.brnz_sales_orders`](../dbt/models/bronze/brnz_sales_orders.sql) | Dòng hàng `(sales_order_id, order_detail_id)` | `SalesOrderHeader` + `SalesOrderDetail` | Ghép header/detail; giữ `order_date`, `customer_id`, `product_id`, `order_qty`, `line_total`. |
| [`silver.slvr_customers`](../dbt/models/silver/slvr_customers.sql) | 1 dòng/`customer_id` | `brnz_customers` | NULL tên → `Unknown`; có `full_name`, `email_promotion`, `territory_id`. |
| [`silver.slvr_products`](../dbt/models/silver/slvr_products.sql) | 1 dòng/`product_id` | `brnz_products` | Bổ sung giá trị thay thế cho color/size/subcategory, cờ `is_discontinued`. |
| [`silver.slvr_sales_orders`](../dbt/models/silver/slvr_sales_orders.sql) | Dòng hàng đủ điều kiện theo order/detail | `brnz_sales_orders` | Lọc `order_qty > 0`, `unit_price >= 0`; tính `order_channel`, `gross_amount`, `effective_unit_price`, `has_discount`. |
| [`gold.gld_customer_metrics`](../dbt/models/gold/gld_customer_metrics.sql) | 1 dòng/`customer_id` | Silver customers + sales | `total_orders`, `total_revenue`, `avg_order_value`, ngày mua đầu/cuối; giữ khách chưa mua. |
| [`gold.gld_product_performance`](../dbt/models/gold/gld_product_performance.sql) | 1 dòng/`product_id` | Silver products + sales | Lượng/doanh thu/lợi nhuận theo sản phẩm; giữ sản phẩm chưa bán. |
| [`gold.gld_sales_summary`](../dbt/models/gold/gld_sales_summary.sql) | 1 dòng/ngày có đơn | `slvr_sales_orders` | Số đơn/khách, doanh thu, online/offline, dòng có giảm giá. |

`total_orders` là `COUNT(DISTINCT sales_order_id)`, không phải số dòng hàng.
`avg_order_value` = doanh thu khách / số đơn phân biệt; `avg_order_line_value`
của summary là trung bình `line_total` theo **dòng**. Profit dùng
`standard_cost` hiện tại, không phải giá vốn lịch sử. Xem công thức và ngữ
nghĩa NULL đầy đủ trong [data lineage](tuan_data_lineage.md#truy-vết-cột-và-công-thức-quan-trọng).

## Hợp đồng dữ liệu và cách tạo docs

[`bronze/schema.yml`](../dbt/models/bronze/schema.yml),
[`silver/schema.yml`](../dbt/models/silver/schema.yml) và
[`gold/schema.yml`](../dbt/models/gold/schema.yml) mô tả từng cột và tests.
[`src_adventureworks.yml`](../dbt/models/bronze/src_adventureworks.yml) mô tả
nguồn, timestamp và freshness. [Test catalog](tuan_test_catalog.md) giải thích
toàn bộ generic/singular tests; GE kiểm tra riêng bảng Silver customer/order.

Tạo bản dbt docs từ checkout đang chạy:

```bash
docker compose exec -T dbt dbt deps
docker compose exec -T dbt dbt docs generate --target dev
```

Artifacts `dbt/target/index.html`, `manifest.json`, `catalog.json` được tạo
tại chỗ và bị Git bỏ qua. `docs generate` cần database kết nối được và models
đã tồn tại. DAG `dbt_transform` cũng tạo docs sau khi dbt tests và GE qua.

## Source freshness

`dbt source freshness --target dev` đo `MAX(ModifiedDate)` của sáu bảng nguồn
so với giờ UTC từ SQL Server. Ngưỡng demo: cảnh báo sau 24 giờ, lỗi sau 48
giờ. AdventureWorks2014 là snapshot lịch sử nên **6/6 ERROR STALE là kết quả
dự kiến**, dù `dbt run`, data tests và GE PASS. Đây là thời điểm thay đổi
nghiệp vụ, không phải ingestion/restore timestamp. Không chỉnh dữ liệu hoặc
nâng ngưỡng lên nhiều năm để làm xanh báo cáo; xem
[finding DQ-W2-01](tuan_week2_quality_report.md).
