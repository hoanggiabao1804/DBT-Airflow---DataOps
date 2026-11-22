# Tuân — hướng dẫn đọc và tạo dbt docs

Tài liệu được khởi tạo ngày 11–12 và cập nhật ngày **18/11/2026** cho ngày 14. Phạm vi hiện tại là **202 dbt tests** sau khi ngày 13 thêm hai kiểm tra bảo toàn tập khóa customer/product; bằng chứng ngày 11–12 có 200 tests là số liệu lịch sử. Xem [lineage và công thức](tuan_data_lineage.md), [danh mục tests và cách xử lý lỗi](tuan_test_catalog.md), [nghiệm thu ngày 13](tuan_week3_day13.md) và [bàn giao ngày 14](tuan_week3_day14.md). Tạo docs không thay thế một lần chạy tests.

## Phạm vi tài liệu

| Nhóm | Nội dung trong dbt docs |
| --- | --- |
| 10 models Bronze → Silver → Gold | Grain, 131 cột đầu ra, phép tính, giá trị mặc định và trường hợp NULL hợp lệ |
| 6 nguồn đang dùng | 59 cột được mô hình tiêu thụ hoặc kiểm tra timestamp; khóa, vai trò và ý nghĩa ModifiedDate |
| 7 khai báo `raw` trong schema `dbo` | Ghi rõ là khai báo cũ, không có model sử dụng, không nằm trong phạm vi validation/freshness |
| 3 generic tests tự viết | Tham số, giá trị mặc định, giới hạn, NULL và ý nghĩa PASS/FAIL |
| Macro freshness SQL Server | Đồng hồ UTC, business watermark, ngưỡng 24/48 giờ và dữ liệu rỗng |

Mô tả nguồn tập trung vào cột pipeline sử dụng; không phải từ điển đầy đủ mọi cột của AdventureWorks. Cột có mô tả không đồng nghĩa cột đó có test riêng. Các model nằm trong [Bronze](../dbt/models/bronze/schema.yml), [Silver](../dbt/models/silver/schema.yml), [Gold](../dbt/models/gold/schema.yml); nguồn hoạt động nằm trong [src_adventureworks.yml](../dbt/models/bronze/src_adventureworks.yml), tài liệu macro nằm trong [macros/schema.yml](../dbt/macros/schema.yml).

## Tạo và xem docs

Chạy từ thư mục gốc repository sau khi SQL Server và service `dbt` sẵn sàng, database đã restore, profiles đã cấu hình và models đã được build. Nếu pipeline vừa chạy `dbt deps`, không cần chạy lại bước đó.

```powershell
docker compose exec -T dbt dbt deps --profiles-dir . --target dev
docker compose exec -T dbt dbt docs generate --profiles-dir . --target dev --target-path target/docs
```

Chỉ dùng kết quả khi lệnh generate trả mã 0. Thư mục `dbt/target/docs/` chứa `index.html`, `manifest.json` và `catalog.json`: manifest lưu mô tả, tests và quan hệ phụ thuộc; catalog đọc metadata cột từ database thực tế. `docs generate` không chạy lại models/tests và không xác nhận freshness hay GE đã đạt. Không commit toàn bộ target; lưu bằng chứng tóm tắt của lần chạy và dùng artifact CI khi cần bàn giao.

Service `dbt` hiện không publish cổng docs. Có thể phục vụ HTML bằng Python trên máy local, rồi mở `http://127.0.0.1:8081`:

```powershell
python -m http.server 8081 --bind 127.0.0.1 --directory dbt/target/docs
```

Trong giao diện, tìm model theo tên, xem phần Columns/Tests và mở biểu đồ lineage. `brnz_example` là view ví dụ độc lập, không phải đầu vào của Silver. Nhánh `raw` không có downstream là khai báo cũ, không phải nguồn thứ hai đang được xử lý. Workflow DBT CI hiện chạy `docs generate` và lưu target trong artifact `dbt-compiled`; artifact của một run chỉ mô tả đúng commit/run đó.

## Đọc đúng hợp đồng dữ liệu

Customer và product có grain một dòng mỗi khóa; sales có grain **một dòng chi tiết đơn hàng**, nên `sales_order_id` lặp lại là bình thường. Gold tính số đơn bằng `count(distinct ...)`; `avg_order_line_value` là trung bình giá trị dòng, khác `avg_order_value` của customer. Profit dùng standard cost hiện tại, không tái tạo giá vốn lịch sử.

Tên customer chỉ thay NULL bằng `Unknown`, rồi ghép bằng một dấu cách; không trim hay chuẩn hóa hoa/thường. `email_promotion` có thể NULL sau left join người mua; customer không có đơn giữ tổng doanh thu/AOV NULL. Product không bán có các tổng NULL; profit có thể âm, margin của sản phẩm đã bán với doanh thu bằng 0 là NULL. Weight được giữ theo đơn vị nguồn, không chuyển đổi đơn vị. Các trường hợp này không được tự sửa thành lỗi.

| Test/kiểm tra | Ý nghĩa và giới hạn |
| --- | --- |
| `positive_values` | Mặc định chấp nhận 0; `allow_zero: false` yêu cầu lớn hơn 0. Bỏ qua NULL; cần `not_null` riêng nếu bắt buộc. |
| `no_future_dates` | Timestamp không được lớn hơn đồng hồ UTC hiện tại, tính cả giờ. Bỏ qua NULL; dữ liệu rất cũ vẫn có thể PASS. Không áp dụng cho ngày dự kiến như due date. |
| `line_total_matches` | Kiểm tra `quantity × unit_price × (1 − discount)`, sai lệch tối đa 0,01 đơn vị tiền tệ; đúng bằng ngưỡng vẫn PASS. NULL, dấu và khoảng discount dùng tests riêng. |
| 6 singular reconciliation tests | Hai kiểm tra tập khóa dimension, một kiểm tra dòng sales đủ điều kiện, ba kiểm tra chỉ số Gold; xem phạm vi từng test trong danh mục. Hai kiểm tra dimension không chứng minh toàn bộ thuộc tính đã được chuyển đổi đúng. |
| Source timestamp tests | 12 tests `not_null`/`no_future_dates` cho ModifiedDate của 6 nguồn; **đã nằm trong 202 dbt tests**. |
| Source freshness | 6 phép đo độc lập, dùng `MAX(ModifiedDate)` so với UTC; mặc định WARN sau 24 giờ, ERROR sau 48 giờ. |

202 dbt tests và 40 GE expectations có phần kiểm tra trùng nhau, không phải 242 quy tắc nghiệp vụ độc lập. GE kiểm tra hai tập dữ liệu Silver customer/order; mô tả ở đây không mở rộng phạm vi GE sang toàn bộ Bronze/Gold.

AdventureWorks2014 là snapshot lịch sử: 6 nguồn stale trong bằng chứng tuần 2 là kết quả thật và vẫn cần được báo lỗi. ModifiedDate là lúc cập nhật nghiệp vụ, không phải lúc restore/ingest. Không đổi timestamp hoặc tăng SLA chỉ để xanh. Khi chạy `scripts/verify_dbt_freshness.ps1`, exit 1 biểu thị dữ liệu stale; exit 2 là lỗi kiểm tra/thực thi cần xử lý. Đọc [hướng dẫn freshness](tuan_week2_day6_7.md) trước khi diễn giải kết quả; PASS tests hoặc GE không xóa kết luận freshness này.

Bằng chứng runtime tham chiếu cho rà soát ngày 14 là lượt Airflow ngày **17/11/2026**: 10 models, 202 tests, 40 GE expectations và 5 tasks thành công. Ngày 14 rà soát tài liệu trên code không đổi so với lượt đó; không có lượt chạy Airflow mới chỉ vì cập nhật Markdown. [Bộ bằng chứng ngày 14](evidence/tuan-week3-day14/20261118/README.md) tách kiểm tra tài liệu khỏi kết quả runtime được tham chiếu.

[Demo ngày 15](tuan_week3_day15_demo.md) có hướng dẫn trình bày và [lượt chạy thử mới ngày 19/11/2026](evidence/tuan-week3-day15/20261119/README.md): dbt, GE, docs và các fixtures chạy thủ công, tuần tự. Kết quả này không được gắn nhãn là một lượt scheduler Airflow mới.
