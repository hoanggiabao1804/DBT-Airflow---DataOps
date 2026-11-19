# Airflow pipeline `dbt_transform`

Tài liệu vận hành chính cho tầng orchestration (người phụ trách: Thịnh). Phần
kiểm thử chất lượng bên trong các task (dbt tests, GX checkpoints, bằng chứng) do
Tuân phụ trách: xem [tuan_week3_day11_12.md](tuan_week3_day11_12.md).

## Luồng xử lý

```text
check_runtime → dbt_deps → dbt_run → dbt_test → ge_validate → dbt_docs
```

| Task | Làm gì | Retries | Timeout |
| --- | --- | ---: | ---: |
| `check_runtime` | Có đúng 1 container `dbt` và 1 `ge-worker` đang chạy; `dbt debug` đăng nhập được SQL Server | 2 (30 s) | 3 phút |
| `dbt_deps` | Cài package dbt (`dbt_utils`) — cần mạng | 3 | 10 phút |
| `dbt_run` | Build 10 models Bronze → Silver → Gold | 2 | 30 phút |
| `dbt_test` | Toàn bộ schema/generic/singular tests | 2 | 20 phút |
| `ge_validate` | 2 checkpoint GX (customer, order) trên schema Silver | 1 | 20 phút |
| `dbt_docs` | `dbt docs generate` — chỉ chạy khi mọi kiểm tra chất lượng đạt | 1 | 10 phút |

Mọi cạnh là `all_success`: một task fail thì mọi task phía sau thành
`upstream_failed`. Không có nhánh "bỏ qua lỗi". Exit 1 (dữ liệu sai) và exit 2 (lỗi
thực thi) của runner đều làm task fail.

### Vì sao có `check_runtime`?

Trước đây nếu container `dbt` chết hoặc SQL Server sập, lỗi chỉ lộ ra trong
`dbt_deps`/`dbt_run` dưới dạng lỗi Docker/ODBC khó đọc. `check_runtime` kiểm tra
trước và in thông báo rõ ràng:

```text
Service ge-worker: expected 1 running container, found 0
dbt debug: FAILED (target dev) - SQL Server down or profile invalid
```

Đã kiểm chứng cả hai trường hợp: [ge-worker dừng](evidence/thinh-week1-day3-4/20261119/check_runtime_ge_worker_down.txt),
[SQL Server dừng](evidence/thinh-week1-day3-4/20261119/check_runtime_sqlserver_down.txt).

## Retry và timeout

- `retry_exponential_backoff=True`, `retry_delay=1 phút`, `max_retry_delay=10 phút`:
  lần thử lại cách nhau khoảng 1 → 2 → 4 phút (Airflow cộng thêm jitter). Lỗi tạm
  thời (SQL Server khởi động lại, mất mạng ngắn) có thời gian tự phục hồi.
- Lỗi **dữ liệu** (dbt test fail, GX fail) không tự hết khi retry. Retries ở `dbt_test`
  và `ge_validate` để chống lỗi hạ tầng, không phải để "thử may". Vì vậy GX chỉ có 1 retry.
- `execution_timeout` cho từng task ≈ 3–5 lần thời gian thực tế (cả DAG ~45 giây trên máy
  dev) nhưng tối thiểu vài phút: timeout nghĩa là **treo**, không phải **chậm**.
- `dagrun_timeout=2h`: một run treo không giữ mãi slot duy nhất (`max_active_runs=1`).
- Mỗi attempt có thư mục bằng chứng riêng (`try-<n>-<uuid>`), retry không ghi đè bằng
  chứng của lần trước.

## Lịch chạy

| Biến môi trường (đặt cho **cả** webserver và scheduler) | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `DATAOPS_SCHEDULE` | `0 6 * * *` | Cron/preset Airflow. `manual`/`none`/`off` = chỉ chạy khi trigger tay |
| `DATAOPS_DBT_TARGET` | `dev` | Target trong `dbt/profiles.yml` |
| `DATAOPS_GE_SCHEMA` | `silver` | Schema GX kiểm tra |

- Timezone của DAG: `Asia/Ho_Chi_Minh`, nên `0 6 * * *` là **06:00 giờ Việt Nam**
  (23:00 UTC hôm trước). Airflow UI mặc định hiển thị UTC.
- `catchup=False`: dataset AdventureWorks là dữ liệu lịch sử, không backfill các ngày đã
  lỡ. Khi bật DAG lần đầu Airflow chỉ tạo **một** run cho khoảng gần nhất.
- `is_paused_upon_creation=True`: DAG mới luôn ở trạng thái tạm dừng cho đến khi có người
  bật. Khi Bảo test deploy/rollback, hãy **pause** DAG để tránh hai tiến trình cùng ghi bảng.

```bash
$DC exec -T airflow-scheduler airflow dags pause dbt_transform
$DC exec -T airflow-scheduler airflow dags unpause dbt_transform
```

## Chạy thủ công và đọc kết quả

```bash
RUN_ID=manual-$(date -u +%Y%m%dT%H%M%SZ)
$DC exec -T airflow-scheduler airflow dags trigger dbt_transform --run-id "$RUN_ID"
$DC exec -T airflow-scheduler airflow tasks states-for-dag-run dbt_transform "$RUN_ID"
$DC exec -T airflow-scheduler python /opt/airflow/scripts/airflow_run_report.py dbt_transform "$RUN_ID"
```

Log: UI → Grid → task → *Logs*, hoặc
`airflow/logs/dag_id=dbt_transform/run_id=<run>/task_id=<task>/attempt=<n>.log`.
Bằng chứng dbt/GX: `great_expectations/uncommitted/airflow/<run-hash>/<task>/try-<n>-<uuid>/`.

## Lịch sử thay đổi

| Ngày | Nhánh | Thay đổi |
| --- | --- | --- |
| 19/11/2026 | `feature/thinh-week1-day1-2` | Baseline: 5/5 task success, 41 s. Thêm `scripts/airflow_run_report.py` |
| 19/11/2026 | `feature/thinh-week1-day3-4` | `check_runtime`, retries/timeout theo task, exponential backoff, `dagrun_timeout`, lịch 06:00 VN |
| 19/11/2026 | `feature/thinh-week1-day5` | E2E `thinh-week1-day5-e2e-01`: 6/6 success, 42,7 s |
