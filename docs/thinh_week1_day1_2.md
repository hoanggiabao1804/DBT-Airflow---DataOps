# Thịnh — Tuần 1, ngày 1–2: kiểm tra Airflow UI, DAG và logs

Vai trò: Pipeline / Observability Engineer (Module 4, 7). Mục tiêu ngày 1–2 theo kế
hoạch nhóm: kiểm tra Airflow UI, DAG và logs; cùng xác nhận pipeline nền chạy được
trước khi sửa bất cứ thứ gì. Kết quả ở đây là **baseline** để so sánh với các thay
đổi ở ngày 3–4.

## Môi trường đã kiểm tra

| Thành phần | Phiên bản / trạng thái |
| --- | --- |
| Airflow | 2.7.1 (`apache/airflow:2.7.1-python3.9`), LocalExecutor, Postgres 13 |
| dbt | dbt-sqlserver 1.8.7 trong container `dbt` |
| Great Expectations | 0.18.22 trong container `ge-worker` |
| SQL Server | 2019 Express, đã restore AdventureWorks2014, login `imrandbtnew` |
| Compose | `docker-compose.yml` + overlay `docker-compose.airflow-quality.yml` của Tuân |

Lệnh khởi động (Linux; `DOCKER_GID` là group của Docker socket):

```bash
export COMPOSE_PROJECT_NAME=dbt_airflow_project
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) AIRFLOW_UID=$(id -u)
DC="docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml"
$DC build
$DC up -d sqlserver dbt
$DC exec -T sqlserver /tmp/restore_db.sh            # chỉ lần đầu
# tạo login dbt: xem "0. NEW_COMPUTER_SETUP.md" bước 2
$DC up -d --wait airflow-scheduler                  # kéo theo init, webserver, ge-worker
```

> Ghi chú: trên máy Thịnh đã có một stack khác chiếm cổng 1433/8080, nên lần
> kiểm tra này chạy với `-p thinh_dataops` và một file override local (không commit)
> map webserver sang cổng 8090, bỏ publish cổng SQL Server. Kết quả không phụ thuộc
> vào tên project vì runner tìm container theo label Compose.

## Checklist ngày 1–2

| # | Kiểm tra | Cách kiểm tra | Kết quả |
| --- | --- | --- | --- |
| 1 | 6 service chạy, health check đạt | `$DC ps` | ✅ [compose_services.txt](evidence/thinh-week1-day1-2/20261119/compose_services.txt) |
| 2 | Airflow UI mở được | `http://localhost:8080` (8090 trên máy Thịnh), `admin`/`admin` | ✅ `/login/` trả 200 |
| 3 | Metadata DB + scheduler healthy | `curl /health` | ✅ [airflow_health.json](evidence/thinh-week1-day1-2/20261119/airflow_health.json) |
| 4 | DAG được parse, không lỗi import | `airflow dags list-import-errors` | ✅ `No data found` |
| 5 | Cấu trúc DAG đúng | `airflow tasks list dbt_transform --tree` | ✅ `dbt_deps → dbt_run → dbt_test → ge_validate → dbt_docs` |
| 6 | DAG chạy end-to-end | trigger `thinh-baseline-20261119-01` | ✅ 5/5 task success, 41 giây |
| 7 | Log từng task đọc được | `airflow/logs/dag_id=…/run_id=…/task_id=…/attempt=N.log` | ✅ |
| 8 | Bằng chứng chất lượng | `great_expectations/uncommitted/airflow/<hash>/…/task_summary.json` | ✅ dbt run 10/10, test 202/202, GX 40/40 |

Kết quả chi tiết: [baseline_run.json](evidence/thinh-week1-day1-2/20261119/baseline_run.json)
(do `scripts/airflow_run_report.py` sinh ra) và
[task_summaries.json](evidence/thinh-week1-day1-2/20261119/task_summaries.json).

| Task | Trạng thái | Lần thử | Thời gian (s) |
| --- | --- | ---: | ---: |
| dbt_deps | success | 1 | 4.4 |
| dbt_run | success | 1 | 7.3 |
| dbt_test | success | 1 | 8.6 |
| ge_validate | success | 1 | 8.8 |
| dbt_docs | success | 1 | 6.5 |

## Đọc log Airflow ở đâu

- **UI**: Grid → chọn ô task → tab *Logs*. Mỗi attempt là một file riêng.
- **Host**: `airflow/logs/dag_id=dbt_transform/run_id=<run>/task_id=<task>/attempt=<n>.log`.
- **Scheduler**: `airflow/logs/scheduler/<ngày>/dbt_dag.py.log` (lỗi parse DAG nằm ở đây).
- Task log chỉ in **một dòng tóm tắt** (`dbt_test: passed, native exit 0 …`) và đường dẫn
  bằng chứng; log đầy đủ của dbt/GX nằm trong `stdout.log` ở thư mục bằng chứng. Đây là
  thiết kế của Tuân để không lộ dữ liệu/credentials vào Airflow log.

Công cụ mới thêm: `scripts/airflow_run_report.py` — chạy trong container scheduler, in
JSON trạng thái/attempt/thời gian của một DAG run, chỉ đọc metadata (không in connection,
biến môi trường hay nội dung log) nên an toàn để commit làm bằng chứng:

```bash
$DC exec -T airflow-scheduler python /opt/airflow/scripts/airflow_run_report.py dbt_transform <run_id>
```

## Những điểm cần cải thiện (đầu vào cho ngày 3–4 và tuần 2)

| # | Hiện trạng | Rủi ro | Hướng xử lý | Khi nào |
| --- | --- | --- | --- | --- |
| 1 | `retries=1`, delay cố định 1 phút cho mọi task | lỗi mạng/DB tạm thời kéo dài > 1 phút làm fail cả run | retries theo từng task + exponential backoff | Ngày 3–4 |
| 2 | Không có lịch (`schedule=None` nếu không đặt env) | pipeline chỉ chạy khi có người bấm | cron mặc định, timezone Việt Nam, vẫn tắt được bằng env | Ngày 3–4 |
| 3 | Không có kiểm tra môi trường trước khi chạy | container chết/DB sập chỉ lộ ra như lỗi Docker trong `dbt_deps` | task `check_runtime` fail nhanh với thông báo rõ | Ngày 3–4 |
| 4 | Không có `dagrun_timeout` | run treo giữ slot (`max_active_runs=1`) vô thời hạn | `dagrun_timeout=2h` | Ngày 3–4 |
| 5 | Không có callback, metric hay thông báo lỗi | lỗi chỉ được phát hiện khi có người mở UI | logging_utils, callbacks, alerting | Tuần 2 |
| 6 | Hủy/timeout task không dừng tiến trình dbt bên trong container (Tuân đã ghi nhận) | tiến trình cũ chạy song song lần retry | kiểm tra trong health check + runbook | Tuần 3 |
