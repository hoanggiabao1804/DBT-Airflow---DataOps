# Chẩn đoán và xử lý lỗi

Chạy các lệnh từ gốc repository. Nếu đã dựng bằng Compose overlay, thêm
`-f docker-compose.yml -f docker-compose.airflow-quality.yml` ngay sau
`docker compose` cho các lệnh quản lý stack. Bắt đầu bằng:

```bash
docker compose ps
docker compose logs --tail=100 sqlserver dbt airflow-scheduler airflow-webserver
docker compose exec -T dbt dbt debug
docker compose exec -T airflow-scheduler airflow dags list-import-errors
```

Đọc **mã thoát, task và artifact của đúng lượt chạy**. Một output xanh của
`dbt run` không thay thế `dbt test`, GE hoặc source freshness.

| Triệu chứng | Kiểm tra / cách xử lý |
| --- | --- |
| `permission denied ... docker.sock` | Người dùng host chưa có quyền Docker. Kiểm tra `docker info`; cấu hình quyền Docker cho host. Với Airflow qua overlay trên Linux, đặt `DOCKER_GID=$(stat -c '%g' /var/run/docker.sock)` rồi tạo lại Airflow services. |
| Container SQL Server không lên hoặc `Login timeout expired` | `docker compose ps sqlserver` và `docker compose logs --tail=100 sqlserver`; chờ SQL Server khởi động, sau đó chạy `docker compose exec -T sqlserver /tmp/restore_db.sh`. Trong container dbt, server là `sqlserver`, không phải `localhost`. Kiểm tra `dbt debug` và target/profile. |
| `Can't open lib 'ODBC Driver 17 for SQL Server'` trên host | ODBC được cài trong dbt container. Chạy `docker compose exec -T dbt dbt debug`/`dbt run`; chỉ cài ODBC trên host nếu chủ ý chạy CLI host. |
| `Invalid object name ... bronze` khi `dbt test` hoặc GE | Source restore chưa đủ, hoặc các models chưa được tạo trong target/schema hiện tại. Chạy `dbt debug`, rồi `docker compose exec -T dbt dbt run` trước `dbt test`; GE cần Silver tables đã có. |
| `dbt source freshness` trả `ERROR STALE`, exit 1 | Đọc `dbt/target/sources.json`: nếu có `max_loaded_at` nhưng trạng thái `error` và không có SQL exception, dữ liệu quá ngưỡng. Sáu nguồn AdventureWorks lịch sử dự kiến stale theo 24/48 giờ; xem [finding DQ-W2-01](tuan_week2_quality_report.md). Không coi đây là lỗi ODBC. |
| Airflow báo `Dag ... could not be found` | Chạy `airflow dags list` và `list-import-errors` trong scheduler. Trên `develop` hiện có DAG `dbt_transform`; tên ví dụ `dbt_bronze_layer_test_alert` trong lab guide chưa phải DAG ở checkout này. Kiểm tra nhánh đã merge và file trong `airflow/dags/`. |
| Airflow task `ge_validate` không tìm được service | DAG tích hợp cần Compose overlay và `ge-worker` healthy. Khởi động bằng lệnh ở [setup guide](setup.md#1-lấy-code-và-chọn-cấu-hình-compose), rồi xem `docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml ps`. |
| Airflow task không gọi được Docker | Kiểm tra bind mount `/var/run/docker.sock`, `DOCKER_GID`, `DATAOPS_COMPOSE_PROJECT`, và đúng một container `dbt`/`ge-worker` đang chạy. Xem `task_summary.json` và `stdout.log` của attempt trong `great_expectations/uncommitted/airflow/`. |
| `Permission denied` tại `dbt/logs/dbt.log` trên host | File có thể do container tạo với UID khác. Dùng CLI trong dbt container như [setup](setup.md); hoặc đặt `DBT_LOG_PATH` vào thư mục host bạn sở hữu. Tránh sửa quyền toàn repo thành `777`. |
| `pre-commit ... (no files to check)` cho `.sql`/`.yml` | Trong Bash dùng `/` (`dbt/models/gold/...`), không dùng dấu `\` của Windows. Xác nhận đường dẫn bằng `git status --short` và chạy lại. |
| Workflow deploy staging lỗi kết nối | Staging job tạo SQL Server **tạm trên GitHub runner**, không dùng `localhost` trên máy bạn. Xem bước start/restore database và artifact của chính run đó; staging không tồn tại sau job. |
| Workflow production bị skip hoặc thiếu secrets | Job production chỉ chạy từ `main` hoặc dispatch production từ `main`. Cần `PROD_SQL_SERVER`, `PROD_SQL_USER`, `PROD_SQL_PASSWORD` trong GitHub environment và database có thể kết nối từ runner. |

## Xử lý lỗi dbt/GE có bằng chứng

1. Với dbt, tìm `status`, `message`, `unique_id` trong
   `dbt/target/run_results.json`; `manifest.json` giúp xác định model/test
   tương ứng. Chạy lại selector hẹp sau khi sửa, rồi chạy toàn bộ tests.
2. Với GE, đọc `summary.json` và hai checkpoint JSON trong output của chính
   lượt chạy. Exit 1 là expectation không đạt; exit 2 thường là lỗi
   input/connection/thực thi. Không cộng kết quả GE vào số dbt tests.
3. Với Airflow, xem trạng thái task, `task_summary.json`, `stdout.log` theo
   DAG run và attempt; lỗi `dbt_test`/`ge_validate` chặn `dbt_docs`.

## Deploy và rollback

[`week3_deployment.md`](week3_deployment.md) ghi chính xác quy trình dev,
staging, production và giới hạn rollback. `backups/` chứa release snapshot
local và được Git bỏ qua. Chỉ chọn release đã qua mọi post checks; rollback
từ source snapshot **không** khôi phục toàn bộ SQL Server. Khi nghi ngờ, xác
minh target, checksum và database trước khi chạy lệnh rollback. Không dùng
`docker compose down -v`, `docker system prune` hoặc xóa volumes làm bước
chẩn đoán mặc định vì chúng có thể xóa dữ liệu và evidence.
