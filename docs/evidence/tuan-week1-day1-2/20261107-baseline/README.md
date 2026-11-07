# Bằng chứng ngày 1–2 của Tuân

Lần chạy ngày **07/11/2026**, Asia/Saigon. Run ID: `20261107T014621770Z-70dbdc1c`. Các timestamps trong JSON là UTC.

- `baseline_status.json`: deps/debug/run/test đều exit 0; baseline `passed`.
- `01_deps.stdout.txt` đến `04_test.stdout.txt`: stdout của từng lệnh; có cảnh báo cấu hình `tests` đổi tên thành `data_tests`.
- `run.run_results.json`: 10 models thành công, command `run`, invocation riêng.
- `test.run_results.json`: 18 tests PASS, command `test`, invocation riêng.
- `model_relations.json`: tên relation/schema từ manifest mới; 4 Bronze views, 3 Silver tables, 3 Gold tables được xác minh thêm bằng truy vấn database.
- `runtime_environment.json`, `database_verification.stdout.txt`, `dbt_login_setup.stdout.txt`: phiên bản, database ONLINE, loại object và thiết lập quyền kết nối.
- `sql_review.stdout.txt`, `sql_review_status.json`: truy vấn review hoàn tất, exit 0; SHA-256 của file SQL và liên kết về baseline. Các dòng `issue_count > 0` là findings nghiệp vụ, không phải kết quả của 18 dbt tests.
- Các file `*.artifact_copy.txt` và `sql_review.copy.txt`: kết quả sao chép artifacts/script.

`database_setup.partial.stdout.txt` là log restore chưa ghi đủ: tiến trình thu log bị dừng sau khi SQL đã báo restore hoàn tất và database ONLINE. File này được giữ nguyên dưới tên `partial`, không dùng làm bằng chứng đầy đủ cho trạng thái cuối. Trạng thái database được truy vấn lại bằng lệnh riêng, exit 0, trong `database_verification.stdout.txt`; baseline dbt và SQL review sau đó đều hoàn tất.

Thư mục `../20261106-baseline/` chỉ có thông tin môi trường được kiểm tra hôm trước, chưa có kết quả chạy baseline. Báo cáo hoàn thành dựa trên thư mục ngày 07/11 này.
