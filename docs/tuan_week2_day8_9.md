# Tuân — Tuần 2, ngày 8–9: Great Expectations

Ngày thực hiện: **16/11/2026**, Asia/Saigon (UTC+7). Nhánh `feature/tuan-week2-day8-9` tách từ `develop` tại `65486bf`, sau khi PR #10 của ngày 6–7 được merge.

Phạm vi theo `Project-Devops.md`: cấu hình Great Expectations, tạo customer/order expectation suites và checkpoint chạy được. Đã hoàn thành hai suites, hai checkpoints, môi trường Docker riêng và runner có mã thoát rõ ràng.

## Kết quả trên SQL Server thật

| Checkpoint | Bảng | Số bản ghi | Kết quả |
| --- | --- | ---: | --- |
| `customer_checkpoint` | `silver.slvr_customers` | 19.820 | 10/10 PASS |
| `order_checkpoint` | `silver.slvr_sales_orders` | 121.317 | 30/30 PASS |

Validation chạy trên toàn bộ bảng, không lấy mẫu. Hai checkpoint trả **exit 0**. Timestamp trong artifacts dùng UTC; lần baseline chạy từ **09:03:14 đến 09:03:23 giờ Việt Nam**. [Kết quả baseline](evidence/tuan-week2-day8-9/20261116/baseline/summary.json).

Runtime đã kiểm chứng: Python 3.11.18, GX 0.18.22, SQLAlchemy 1.4.54, pyodbc 5.2.0 và ODBC Driver 17. Image được build thật và `pip check` không phát hiện xung đột. Dependencies chính được pin trong `great_expectations/requirements.txt`; container tách riêng dbt/Airflow. [Phiên bản runtime](evidence/tuan-week2-day8-9/20261116/runtime.json).

## Quy tắc dữ liệu

- **Customer:** đủ 8 cột, bảng không rỗng, khóa không NULL/không trùng, các trường tên không NULL, email preference thuộc 0/1/2 khi có giá trị, timestamp bắt buộc và không tương lai. `Unknown` và preference NULL hợp lệ; suite không kiểm tra định dạng/trim tên.
- **Order:** đủ 20 cột, bảng không rỗng, 16 trường bắt buộc, khóa ghép `(sales_order_id, order_detail_id)`, quantity > 0, giá/doanh thu >= 0, discount trong `[0,1]`, status 1–6, channel Online/Offline, discount flag 0/1 và timestamp không tương lai.
- Một order có nhiều dòng được chấp nhận. Giá bằng 0, discount 100%, ship date NULL và due date tương lai được giữ đúng theo semantics của dbt.

Mỗi expectation có `meta.rule_id` để xác định lỗi và đối chiếu fixtures. Các công thức doanh thu, khóa ngoại và đối chiếu tầng dữ liệu vẫn thuộc các tests dbt đã có. GE ở bước này kiểm tra chất lượng đầu ra Silver; không thay thế kiểm tra nguồn Bronze hay freshness.

## Kiểm thử dữ liệu sai và mã thoát

**8/8 tình huống khớp kỳ vọng**, với đúng rule IDs, số dòng vi phạm và row counts. Bảy tình huống dữ liệu chạy đủ 40 expectations mỗi tình huống; tình huống thiếu bảng kiểm tra lỗi thực thi riêng.

| Tình huống | Kết quả mong đợi, đã xác nhận |
| --- | --- |
| Nullable hợp lệ, nhiều dòng/đơn, hàng miễn phí, giảm 100%, đủ status 1–6 | PASS, exit 0 |
| Trùng customer key và order composite key | FAIL, mỗi rule bắt 2 dòng |
| NULL ở 21 trường bắt buộc của hai suites | FAIL, đúng 21 rules, mỗi rule 1 dòng |
| Sai email preference, status, channel, discount flag | FAIL, đúng 4 rules |
| Quantity 0/âm, giá/doanh thu âm, discount ngoài [0,1] | FAIL, đúng 6 rules |
| Customer/order/ship timestamp trong tương lai | FAIL, đúng 3 rules |
| Cả hai bảng rỗng | FAIL, 2 nonempty rules, exit 1 |
| Thiếu bảng order | Lỗi thực thi, exit 2; không được tính là PASS |

Đã gọi CLI thật để xác minh cả ba mã thoát **0/1/2**. Fixture tổng hợp trả thành công khi các nhánh PASS/FAIL/error khớp kỳ vọng; không bỏ qua lỗi ngoài dự kiến. Bảng thử nằm trong schema UUID riêng, và đã xác minh schema được dọn bằng connection mới. Không sửa dữ liệu Silver thật. [Tổng hợp fixtures](evidence/tuan-week2-day8-9/20261116/contracts/summary.json).

Python đã qua Black, Flake8 và kiểm tra cú pháp. SHA-256 của context/suites/checkpoints và runner trong evidence khớp files được thực thi.

## Chạy lại và bàn giao

[Hướng dẫn chạy bằng Docker Compose](../great_expectations/README.md) gồm lệnh build image, chạy cả hai checkpoint, chọn checkpoint riêng, chạy fixtures và cấu hình target/schema. Output nằm tại `great_expectations/uncommitted/`, được Git bỏ qua; báo cáo tổng hợp cần bàn giao được lưu riêng trong `docs/evidence/`.

Runner dùng connection từ target dbt đã chọn, giữ credentials trong bộ nhớ, xuất thống kê thay vì tên khách hoặc dòng dữ liệu lỗi. Native GX stores được tạo trong context tạm; kết quả tổng hợp và hash cấu hình được giữ lại trước khi context được dọn. Chưa dựng Data Docs HTML.

Các workflow CI hiện tại vẫn kiểm tra dbt/Python như trước; **chưa tự chạy GE trong CI hoặc Airflow**. Phần tích hợp DAG sẽ phối hợp với Thịnh theo kế hoạch. Nguồn AdventureWorks lịch sử vẫn stale ở freshness ngày 6–7; GE PASS không chứng minh dữ liệu mới.

**Việc tiếp theo của Tuân trong tuần 2: ngày 10 — kiểm tra kết quả validation và lập báo cáo chất lượng dữ liệu.** Báo cáo này ghi nhận nghiệm thu triển khai ngày 8–9; chưa thay cho báo cáo chất lượng tổng hợp ngày 10.
