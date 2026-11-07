# Tuân — Kết quả ngày 1–2, tuần 1

Ngày thực hiện: **06–07/11/2026**, múi giờ Asia/Saigon. Nhánh: `feature/tuan-week1-day1-2`, bắt đầu từ commit `08b3b7e` trên `main` vì repository local chưa có nhánh `develop`.

Phạm vi theo tài liệu phân công local `Project-Devops.md`: kiểm tra kết nối bằng `dbt debug`, chạy `dbt run`, chạy `dbt test` và rà soát các models Bronze/Silver/Gold. Tests mới thuộc ngày 3–4; sửa các KPI sau khi đối chiếu nằm trong danh sách bàn giao ngày 5.

## Kết quả thực thi

**Đã hoàn thành phạm vi ngày 1–2:** kết nối thành công, 10/10 models chạy thành công, 18/18 tests PASS và đã review các models bằng code lẫn truy vấn dữ liệu. Các KPI đếm đơn/AOV có sai lệch theo định nghĩa đơn hàng riêng biệt; cần xử lý ở bước tiếp theo dù bộ tests hiện tại đều PASS.

Baseline chạy từ **08:46:22 đến 08:47:54 ngày 07/11/2026** (Asia/Saigon). [Trạng thái từng lệnh](evidence/tuan-week1-day1-2/20261107-baseline/baseline_status.json) ghi exit code và thời gian; bằng chứng được tạo mới, không lấy từ `dbt/target` hoặc `dbt/logs` cũ.

| Bước | Trạng thái |
| --- | --- |
| Docker / services | Hai images đã build; services `sqlserver`, `dbt` đã chạy. |
| Restore AdventureWorks2014 | **ONLINE**, SQL Server 15.0.4500.2 Express; [xác minh database](evidence/tuan-week1-day1-2/20261107-baseline/database_verification.stdout.txt). Login/user theo profile local đã được thiết lập theo hướng dẫn setup của project. |
| `dbt deps` | **Exit 0**, cài `dbt_utils` 1.1.1. |
| `dbt debug` | **Exit 0**, `All checks passed`, kết nối SQL Server thành công. |
| `dbt run` | **10/10 thành công**, 4 views + 6 tables; ERROR=0, SKIP=0. [Kết quả từng model](evidence/tuan-week1-day1-2/20261107-baseline/run.run_results.json). |
| `dbt test` | **18/18 PASS**, ERROR=0, SKIP=0. [Kết quả từng test](evidence/tuan-week1-day1-2/20261107-baseline/test.run_results.json). |
| Review 10 models | Hoàn tất lineage, grain/khóa, tests và các vấn đề logic. |
| Đối chiếu số liệu SQL | **Exit 0**, đã kiểm tra đủ 6 bảng nguồn và 10 models; [kết quả truy vấn](evidence/tuan-week1-day1-2/20261107-baseline/sql_review.stdout.txt). |

[Môi trường thực tế](evidence/tuan-week1-day1-2/20261107-baseline/runtime_environment.json): Python 3.9.25, dbt-core/dbt-sqlserver 1.8.7, ODBC Driver 17 (gói 17.11.1.1-1), target `dev`, 4 threads. [Manifest mới](evidence/tuan-week1-day1-2/20261107-baseline/model_relations.json) xác nhận schema vật lý là **`bronze`, `silver`, `gold`**. Có cảnh báo dbt đổi tên cấu hình `tests` thành `data_tests`; cảnh báo này không làm thất bại baseline.

## Kết quả đối chiếu dữ liệu

Dữ liệu nguồn có **31.465 đơn hàng**, **121.317 dòng hàng**, **19.820 khách hàng**, **504 sản phẩm**. Ngày đặt hàng từ **31/05/2011 đến 30/06/2014**; `SalesOrderHeader.ModifiedDate` mới nhất là **07/07/2014**. Đây là dữ liệu mẫu lịch sử, cần tính đến khi thiết kế source freshness ở tuần 2.

| Tầng | Model | Số dòng |
| --- | --- | ---: |
| Bronze | `brnz_customers` | 19.820 |
| Bronze | `brnz_example` | 19.820 |
| Bronze | `brnz_products` | 504 |
| Bronze | `brnz_sales_orders` | 121.317 |
| Silver | `slvr_customers` | 19.820 |
| Silver | `slvr_products` | 504 |
| Silver | `slvr_sales_orders` | 121.317 |
| Gold | `gld_customer_metrics` | 19.820 |
| Gold | `gld_product_performance` | 504 |
| Gold | `gld_sales_summary` | 1.124 |

Các truy vấn đã chạy không phát hiện khóa dòng hàng trùng/NULL, tham chiếu khách hàng/sản phẩm bị thiếu, dòng hợp lệ bị mất hoặc dòng không hợp lệ lọt vào Silver. Có **0 dòng bị lọc** trên bộ dữ liệu hiện tại. Tổng doanh thu Silver và Gold sales summary cùng bằng **`109846381.399888`**; doanh thu và tổng đơn riêng biệt theo ngày cũng khớp.

Ba nhóm KPI cần xử lý sau khi thống nhất định nghĩa theo đơn hàng:

| KPI | Kỳ vọng theo đơn riêng biệt | Kết quả Gold hiện tại | Phạm vi sai lệch |
| --- | ---: | ---: | --- |
| `online_orders` | 27.659 | 60.398 | 397 ngày |
| `offline_orders` | 3.806 | 60.919 | 40 ngày |
| `orders_with_discount` | 916 | 3.282 | 243 khách hàng |
| `avg_order_value` | Doanh thu / số đơn riêng biệt | Đang tính AVG theo dòng hàng | 15.913 khách hàng lệch quá 0,01 |

Số ngày lệch online/offline có thể trùng nhau, không cộng hai con số này thành tổng ngày duy nhất. Truy vấn so AOV với công thức dòng hàng hiện tại có **0 sai lệch**, xác nhận nguyên nhân là cách định nghĩa grain. Bộ 18 tests hiện có chủ yếu kiểm tra khóa và NULL, chưa kiểm tra những KPI này.

Kiểm tra product margin tìm thấy **0 sản phẩm có quantity > 0 và doanh thu = 0** trên dữ liệu hiện tại. Rủi ro chia cho 0 trong code vẫn cần xử lý khi xuất hiện dữ liệu như vậy.

## Sản phẩm bàn giao

- [Review 10 models](tuan_week1_day1_2_model_review.md): sơ đồ luồng dữ liệu, grain/khóa, 18 tests hiện có, các vấn đề logic và danh sách việc ngày 3–5.
- [Script chạy baseline](../scripts/verify_dbt_baseline.ps1): chạy `deps → debug → run → test`, dừng khi lỗi, lưu exit code/thời gian/stdout và kết quả riêng cho run/test. Logs và target của lần chạy nằm trong `/tmp` của container để không ghi đè artifacts cũ đang được Git theo dõi.
- [Truy vấn kiểm tra dữ liệu](../scripts/sql/review_dbt_models.sql): đếm dòng 10 models; kiểm tra khóa, quan hệ, dòng bị lọc ở Silver; đối chiếu doanh thu và KPI Gold. `issue_count > 0` là phát hiện cần review, không phải kết quả của bộ dbt tests hiện có.
- [Script chạy SQL review](../scripts/review_dbt_models.ps1): lấy schema từ baseline mới đã thành công, chạy truy vấn trong service SQL Server và lưu kết quả UTF-8 cùng exit code.
- [Bằng chứng lần chạy ngày 07/11](evidence/tuan-week1-day1-2/20261107-baseline/README.md): runtime, logs, kết quả riêng cho RUN/TEST và kết quả đối chiếu SQL.

## Thay đổi để dựng môi trường

1. `dbt/Dockerfile`: dùng gói cấu hình repository Microsoft tương ứng với `/etc/os-release`, thay cho kho Debian 10 cố định. Base Python hiện resolve thành Debian 13; gói cấu hình lấy đúng repository và khóa ký. Giữ nguyên dbt-core/dbt-sqlserver 1.8.7 và ODBC Driver 17; bổ sung dependency GSSAPI.
2. `sqlserver/Dockerfile`: chuyển CRLF trong `restore_db.sh` thành LF trong image trước khi cấp quyền thực thi, để script từ Windows chạy được trên Linux. Dùng thư viện chạy `unixodbc` thay cho `unixodbc-dev` và bỏ các gói khuyến nghị; service chỉ chạy `sqlcmd`, không cần bộ biên dịch C.

Căn cứ cấu hình ODBC: [hướng dẫn Microsoft](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server?view=sql-server-ver17#previous-versions), [khóa ký repository](https://learn.microsoft.com/en-us/linux/packages#how-to-use-the-gpg-repository-signing-key).

## Cách chạy lại baseline

Sau khi services `sqlserver`, `dbt` đã chạy và database/login trong profile đã được thiết lập:

```powershell
docker compose ps
$evidence = 'docs/evidence/tuan-week1-day1-2/' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
.\scripts\verify_dbt_baseline.ps1 -OutputDirectory $evidence
.\scripts\review_dbt_models.ps1 -EvidenceDirectory $evidence
```

Script tự tạo một thư mục mới dưới `docs/evidence/tuan-week1-day1-2/`. Có thể chỉ định `-OutputDirectory` đến một thư mục chưa có baseline trước đó. Đọc `baseline_status.json` để biết trạng thái/exit code; đọc `run.run_results.json` và `test.run_results.json` để xem kết quả từng model/test.

Khi chạy truy vấn SQL, lấy schema vật lý từ `model_relations.json` trong **lần baseline mới**, truyền vào ba biến `BronzeSchema`, `SilverSchema`, `GoldSchema`. Không lấy schema từ manifest cũ. `sqlcmd -b` báo lỗi thực thi SQL; cần đọc riêng các dòng `issue_count` để đánh giá chất lượng dữ liệu.

## Bàn giao ngày 3–5

- Bổ sung schema tests cho Bronze customers/products/example và relationship tests orders → customers/products; giữ đúng khóa theo dòng hàng.
- Viết và áp dụng ít nhất 3 custom generic tests phù hợp cột hiện có.
- Chốt định nghĩa KPI `avg_order_value`, số đơn theo kênh và số đơn giảm giá; sửa SQL và thêm tests nghiệp vụ theo kết quả đối chiếu.
- Xử lý mẫu số doanh thu bằng 0 khi tính product margin; thống nhất NULL/0 cho khách hàng hoặc sản phẩm chưa có giao dịch.
- Phối hợp Bảo về phiên bản môi trường: `requirements.txt` khai báo core 1.7.3 khác Dockerfile 1.8.7; phối hợp Thịnh chạy DAG end-to-end khi nghiệm thu chung.

SQL/YAML models và tests hiện có được giữ nguyên trong lần baseline này. Các scripts đã được chạy thực tế trên Windows PowerShell; script SQL review đã xử lý cách PowerShell 5.1 đọc mảng JSON. Thay đổi xuống dòng do `dbt deps` tạo trong các packages đang được Git theo dõi đã được hoàn nguyên sau khi xác nhận không có khác biệt nội dung.

Source freshness và Great Expectations theo lịch tuần 2–3. Kết quả ngày 1–2 không thay thế checkpoint cuối tuần về 3 generic tests, PR/CI và Airflow end-to-end.
