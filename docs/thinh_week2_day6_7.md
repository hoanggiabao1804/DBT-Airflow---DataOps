# Thịnh — Tuần 2, ngày 6–7: logging utilities, metrics, Airflow callbacks

Module 4 (Monitoring), phần 1. Mục tiêu: mọi thay đổi trạng thái của task/DAG để lại
**một bản ghi có cấu trúc**, đọc được bằng máy, không cần mở Airflow UI.

## Thành phần mới

```text
airflow/dags/
├── .airflowignore          # bỏ qua utils/ khi scheduler quét DAG
├── dbt_dag.py              # gắn callbacks
└── utils/
    ├── __init__.py
    ├── logging_utils.py    # structured log + metrics file
    └── callbacks.py        # on_execute/success/retry/failure + DAG success/failure
airflow/tests/test_logging_utils.py   # 9 unit tests, chạy không cần Airflow
```

### `logging_utils.py`

| Hàm | Vai trò |
| --- | --- |
| `context_fields(context, dag_level=False)` | Rút `dag_id, run_id, task_id, try_number, duration, log_url, exception_type…` từ context Airflow. Message lỗi bị cắt 500 ký tự, không in traceback/dữ liệu |
| `log_event(event, context, **extra)` | In **một dòng** `DATAOPS_EVENT {json}` vào task log |
| `record_metric(event, context)` | `log_event` + ghi thêm vào `$DATAOPS_METRICS_DIR/task_metrics.jsonl` |
| `read_metrics(path, since)` / `summarize_metrics(records)` | Đọc lại file metrics, tính số lần success/failure/retry, tỉ lệ thành công, thời gian trung bình/max từng task |

Thiết kế cần nhớ:

- **Chỉ dùng thư viện chuẩn** → import được trong scheduler, trong unit test và script host.
- **Không bao giờ raise**: callback lỗi (ví dụ ổ đĩa đầy) chỉ ghi warning; không được biến
  task thành công thành thất bại, hay che mất lỗi gốc.
- Ghi file bằng một lệnh `os.write` với `O_APPEND` → nhiều task ghi đồng thời không bị
  trộn dòng.
- Mặc định `DATAOPS_METRICS_DIR=/opt/airflow/logs/dataops_metrics` (volume `airflow/logs`
  đã mount sẵn, đã nằm trong `.gitignore`).

### `try_number` — một chỗ dễ sai

Trong Airflow 2.7, khi task đã kết thúc thì `ti.try_number` trả về số của **lần thử tiếp
theo**. Trong callback, lần thử vừa chạy là `ti._try_number`. `context_fields` dùng giá trị
này, nên metrics ghi `1, 2, 3` cho ba lần thử chứ không phải `2, 3, 4`.

### DAG callback và task instance

Airflow truyền vào DAG callback context của **task cuối cùng**. Lần chạy thử đầu tiên ghi
nhầm `task_id=dbt_docs` cho sự kiện `dag_success`. Đã sửa: `dag_level=True` bỏ qua task
instance và tính thời gian từ `dag_run.start_date/end_date` (có unit test).

## Kiểm chứng trên Airflow thật

| Run | Kịch bản | Bản ghi metrics |
| --- | --- | --- |
| `thinh-week2-day6-7-success-01` | bình thường | 6 × `task_success` + `dag_success` (44,2 s) |
| `thinh-week2-day6-7-failure-01` | dừng `ge-worker` trước khi trigger | `task_retry` (try 1), `task_retry` (try 2), `task_failure` (try 3), `dag_failure` (177,7 s) |

Run lỗi cho thấy cả exponential backoff: 3 lần thử `check_runtime` kéo dài ~3 phút với
`retry_delay=30s`.

Bằng chứng: [task_metrics.jsonl](evidence/thinh-week2-day6-7/20261119/task_metrics.jsonl),
[success_run.json](evidence/thinh-week2-day6-7/20261119/success_run.json),
[failure_run.json](evidence/thinh-week2-day6-7/20261119/failure_run.json),
[dòng DATAOPS_EVENT trong task log](evidence/thinh-week2-day6-7/20261119/failure_task_log_events.txt).

Tổng hợp bằng `summarize_metrics` trên hai run: 6 success, 2 retry, 1 failure, tỉ lệ
thành công task 85,7 %.

## Cách xem

```bash
# Trên host
tail -f airflow/logs/dataops_metrics/task_metrics.jsonl
grep -h DATAOPS_EVENT airflow/logs/dag_id=dbt_transform/run_id=<run>/task_id=*/attempt=*.log

# Unit tests (máy dev, không cần Airflow)
python -m pytest airflow/tests -q
```

Ngày 8–9: dùng chính các callback này để **gửi thông báo** (alerting.py) và đọc metrics
trong monitoring DAG.
