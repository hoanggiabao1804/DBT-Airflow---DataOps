# Thịnh — Tuần 1, ngày 3–4: dependencies, retries, schedule

Phạm vi: cải thiện `airflow/dags/dbt_dag.py` dựa trên các điểm yếu ghi nhận ở
[ngày 1–2](thinh_week1_day1_2.md). Tài liệu vận hành đầy đủ: [airflow_pipeline.md](airflow_pipeline.md).

## Thay đổi

| Trước | Sau | Lý do |
| --- | --- | --- |
| 5 task, bắt đầu bằng `dbt_deps` | thêm `check_runtime` ở đầu | fail nhanh, thông báo rõ khi container/DB không sẵn sàng |
| `retries=1`, delay cố định 1 phút cho mọi task | retries theo task (deps 3, run/test 2, GX/docs 1) + exponential backoff, tối đa 10 phút | lỗi mạng/DB tạm thời có thời gian hồi phục; lỗi dữ liệu không retry vô ích |
| `execution_timeout` 20 phút cho mọi task | 3–30 phút theo task | timeout phản ánh "treo" của từng bước |
| không có `dagrun_timeout` | 2 giờ | run treo không chiếm mãi slot `max_active_runs=1` |
| `schedule=None` trừ khi đặt env | mặc định `0 6 * * *` giờ Việt Nam, tắt bằng `DATAOPS_SCHEDULE=manual` | pipeline tự chạy hằng ngày; vẫn giữ lựa chọn chạy tay của Tuân |
| `start_date` 2024 (UTC) | `2026-11-01` Asia/Ho_Chi_Minh | cron hiểu theo giờ địa phương |
| owner `tuan` | owner `dataops` | DAG là tài sản chung của nhóm |

Giữ nguyên: runner `scripts/run_airflow_quality_task.py` của Tuân, thứ tự
`deps → run → test → ge → docs`, `catchup=False`, `max_active_runs=1`, paused khi tạo mới.

## Kiểm chứng

| Kiểm tra | Kết quả |
| --- | --- |
| Black / Flake8 (giống CI `python-quality.yml`) | ✅ |
| `airflow dags list-import-errors` | ✅ không có lỗi |
| `airflow tasks list --tree` | ✅ `check_runtime → dbt_deps → … → dbt_docs` |
| Lịch: bật DAG → Airflow tự tạo run `scheduled__2026-11-17T23:00:00+00:00` (06:00 VN ngày 18/11) | ✅ 6/6 success, 42 s — [scheduled_run.json](evidence/thinh-week1-day3-4/20261119/scheduled_run.json) |
| `max_tries` mỗi task đúng cấu hình (2/3/2/2/1/1) | ✅ trong `scheduled_run.json` |
| `check_runtime` khi dừng `ge-worker` | ✅ fail ngay, `found 0` — [log](evidence/thinh-week1-day3-4/20261119/check_runtime_ge_worker_down.txt) |
| `check_runtime` khi dừng SQL Server | ✅ fail, `Connection test: [ERROR]` — [log](evidence/thinh-week1-day3-4/20261119/check_runtime_sqlserver_down.txt) |

Hai kiểm tra lỗi dùng `airflow tasks test` (chạy task một lần, không ghi trạng thái vào
metadata) để không tạo run fail giả trong lịch sử DAG.
