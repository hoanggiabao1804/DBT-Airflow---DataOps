# Thịnh — Tuần 2, ngày 8–9: failure notifications, monitoring DAG, GE integration DAG

Module 4 (Monitoring), phần 2. Ngày 6–7 đã có **ghi nhận** (log + metrics); ngày 8–9 thêm
**báo động** (alert) và **giám sát chủ động** (monitoring DAG), cùng một DAG GE độc lập
hỗ trợ phần Data Quality của Tuân.

## Thành phần mới

```text
airflow/dags/
├── dbt_dag.py              # dùng utils/pipeline.py, thêm SLA + sla_miss_callback
├── monitoring_dag.py       # NEW  dataops_monitoring, mỗi 30 phút
├── ge_quality_dag.py       # NEW  ge_data_quality, mỗi 6 giờ hoặc trigger tay
└── utils/
    ├── alerting.py         # NEW  send_alert(): alert log + webhook + email
    ├── monitoring.py       # NEW  các hàm kiểm tra sức khỏe (thuần, unit-test được)
    ├── pipeline.py         # NEW  CHECK_RUNTIME, runner_env, resolve_schedule dùng chung
    └── callbacks.py        # gửi alert khi retry/fail/SLA miss
scripts/alert_webhook_receiver.py   # webhook giả lập Slack để test/demo
airflow/tests/test_alerting_monitoring.py   # 18 tests (tổng 27)
```

## 1. Alerting (`utils/alerting.py`)

`send_alert(title, message, severity, context)` ghi một bản ghi và gửi tới các kênh:

| Kênh | Bật bằng | Ghi chú |
| --- | --- | --- |
| Alert log | luôn bật | `airflow/logs/dataops_alerts/alerts.jsonl` — audit trail, hoạt động cả khi offline |
| Webhook | `DATAOPS_ALERT_WEBHOOK_URL` | `DATAOPS_ALERT_WEBHOOK_FORMAT=slack \| discord \| teams \| generic` |
| Email | `DATAOPS_ALERT_EMAIL` + cấu hình SMTP của Airflow | dùng `airflow.utils.email.send_email` |

Nguyên tắc:

- Gửi thông báo thất bại **không bao giờ** làm đổi trạng thái pipeline; kết quả gửi được ghi
  vào `delivery` (`sent`, `disabled`, `http_500`, `error_URLError`…).
- URL webhook là **secret** (Slack/Discord nhúng token trong URL): chỉ đọc từ biến môi trường,
  không in ra log, không lưu vào bản ghi lỗi. Đặt trong `.env` (đã bị `.gitignore`), không commit.
- Mỗi alert kèm DAG/task/run/attempt, link log Airflow và đường dẫn runbook.

### Khi nào có alert

| Sự kiện | Mức | Nguồn |
| --- | --- | --- |
| Task retry | warning | `on_task_retry` (tắt bằng `DATAOPS_ALERT_ON_RETRY=false`) |
| Task fail hẳn | critical | `on_task_failure` |
| DAG fail vì lý do **khác** task fail (vd. `dagrun_timeout`) | critical | `on_dag_failure` — một sự cố chỉ báo một lần |
| `dbt_docs` xong muộn hơn 1 h sau cuối interval (run theo lịch) | warning | `sla_miss_callback` |
| Health check đổi trạng thái / sự cố kéo dài > 6 h / phục hồi | critical/warning/info | `dataops_monitoring` |
| GX thất bại | critical | `ge_data_quality.publish_quality_report` |

### Cấu hình Slack/Discord thật

```bash
# .env ở gốc repo (không commit)
DATAOPS_ALERT_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
DATAOPS_ALERT_WEBHOOK_FORMAT=slack          # discord: dùng URL .../api/webhooks/... và format discord
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml up -d airflow-webserver airflow-scheduler
```

Không có Slack? Dùng receiver giả lập (cách nhóm kiểm thử ở đây):

```bash
docker run -d --name alert-receiver --network <project>_dbt_airflow_network --network-alias alert-receiver \
  --user "$(id -u):0" --entrypoint python -v "$PWD/scripts:/s:ro" -v "$PWD/airflow/logs:/out" \
  <project>-airflow-quality:2.7.1 /s/alert_webhook_receiver.py --output /out/webhook_received.jsonl
DATAOPS_ALERT_WEBHOOK_URL=http://alert-receiver:9099/alert DATAOPS_ALERT_WEBHOOK_FORMAT=slack \
  docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml up -d airflow-webserver airflow-scheduler
```

## 2. Monitoring DAG `dataops_monitoring`

```text
check_services ─┐
check_pipeline ─┤
check_metrics  ─┼─> publish_report (all_done)
check_disk     ─┘
```

| Check | Critical | Warning |
| --- | --- | --- |
| services | một trong 6 service không chạy hoặc `unhealthy` | — |
| pipeline | run `dbt_transform` gần nhất **failed**; hoặc DAG đang bật lịch mà lần success cuối > 26 h | DAG bị pause/không có lịch và success cuối quá cũ |
| metrics | — | tỉ lệ task success của `dbt_transform` trong 24 h < 80 % |
| disk | < 2 GB trống ở `logs`/`quality_evidence` | < 5 GB |

- Ngưỡng chỉnh qua env: `DATAOPS_PIPELINE_MAX_AGE_HOURS`, `DATAOPS_MIN_TASK_SUCCESS_RATE`,
  `DATAOPS_DISK_MIN_FREE_GB`, `DATAOPS_DISK_WARN_FREE_GB`.
- Kết quả: `airflow/logs/dataops_monitoring/latest.json` (trạng thái hiện tại) và `history.jsonl`.
- **Chống spam**: chỉ alert khi trạng thái tổng **thay đổi** (ok → critical, critical → ok…);
  sự cố kéo dài thì nhắc lại mỗi 6 giờ. Khi hết lỗi gửi alert `info` "recovered".
- Check không fail khi phát hiện vấn đề — nó *trả về* kết quả. Task của monitoring DAG chỉ fail
  khi chính monitor bị hỏng, và trường hợp đó có alert riêng qua callback.
- `is_paused_upon_creation=False`: monitor không cần ai bật.

## 3. GE integration DAG `ge_data_quality`

```text
wait_for_transform_idle → check_runtime → ge_validate → publish_quality_report (all_done)
```

- `dbt_transform` đã chạy GX ngay sau `dbt_test` (Tuân, ngày 11–12) như **cổng chặn** trước docs.
  DAG này trả lời câu hỏi khác: *dữ liệu **bây giờ** còn hợp lệ không?* — chạy mỗi 6 giờ
  (`DATAOPS_GE_SCHEDULE`) hoặc trigger tay khi điều tra sự cố.
- `wait_for_transform_idle`: sensor mode `reschedule` (không giữ worker slot), chờ khi
  `dbt_transform` đang rebuild bảng để tránh báo lỗi giả.
- `ge_validate`: dùng nguyên runner/bằng chứng của Tuân (`run_airflow_quality_task.py ge`).
- `publish_quality_report`: đọc `task_summary.json` + `ge/summary.json`, ghi metric
  `data_quality` cho từng checkpoint, gửi **một** alert critical có chi tiết số expectation
  đạt/không đạt. `ge_validate` chỉ ghi metric khi fail (không alert chung chung lần hai).
- Param `schema` (mặc định `silver`, regex kiểm tra tên) để kiểm tra schema khác, ví dụ bản
  restore hoặc schema diễn tập `dq_drill` (ngày 10).

## Kiểm chứng trên Airflow (19/11/2026)

| Run | Kết quả |
| --- | --- |
| `dataops_monitoring` `scheduled__2026-11-19T08:00:00+00:00` | phát hiện run `thinh-week2-day6-7-failure-01` fail → **CRITICAL**, webhook `sent` |
| `dbt_transform` `thinh-week2-day8-9-transform-01` | 6/6 success |
| `ge_data_quality` `scheduled__2026-11-18T23:30:00+00:00` và `thinh-week2-day8-9-ge-01` | 4/4 success; customer 10/10, order 30/30 |
| `dataops_monitoring` `thinh-week2-day8-9-monitor-recovery` | mọi check OK → alert **info "recovered"** |

Bằng chứng trong [evidence/thinh-week2-day8-9/20261119](evidence/thinh-week2-day8-9/20261119/):
`alerts.jsonl`, `webhook_received.jsonl` (đúng nội dung Slack nhận được),
`monitoring_history.jsonl`, `monitoring_report_log.txt`, `data_quality_metrics.jsonl`,
`ge_report_log.txt`, và report JSON của từng run.

Tin nhắn webhook (format `slack`) thực tế nhận được:

```text
🚨 [CRITICAL] DataOps health CRITICAL: pipeline=last run thinh-week2-day6-7-failure-01 failed
Environment: development
DAG: dataops_monitoring
...
Runbook: docs/incident_runbook.md
```

## File của thành viên khác đã chạm vào

- `docker-compose.airflow-quality.yml` (Tuân): thêm 8 biến môi trường `DATAOPS_*`/`AIRFLOW_ENV`
  vào anchor chung, mặc định rỗng → hành vi cũ không đổi.
- `.env.example` (Bảo): thêm khối biến alerting dạng comment.
