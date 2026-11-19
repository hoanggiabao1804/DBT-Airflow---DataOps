# Hướng dẫn demo cuối dự án (ngày 15)

Demo **một quy trình DataOps liền mạch** theo mục 6 của kế hoạch nhóm, không demo 7 module rời
rạc. Tổng thời lượng gợi ý: 20–25 phút.

| # | Phần | Người trình bày | Thời gian |
| --- | --- | --- | --- |
| 1 | Developer mở PR → CI tự chạy lint + tests | Bảo | 4' |
| 2 | CI pass → merge `develop` → CD tự động | Bảo | 3' |
| 3 | dbt Bronze → Silver → Gold, tests, GE, smoke tests | Tuân | 5' |
| 4 | Airflow + monitoring: DAG, log, kết quả, thông báo lỗi thử nghiệm | **Thịnh** | 5' |
| 5 | Health check + recovery: phát hiện, xử lý, khôi phục | **Thịnh** (+ Bảo phần rollback) | 5' |
| — | Hỏi đáp | cả nhóm | |

## Chuẩn bị (trước demo 30 phút)

```bash
cd DBT-Airflow---DataOps
export COMPOSE_PROJECT_NAME=dbt_airflow_project
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) AIRFLOW_UID=$(id -u)
DC="docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml"
AF="$DC exec -T airflow-scheduler airflow"

# 1. Webhook nhận alert: Slack/Discord thật trong .env, HOẶC receiver giả lập
docker run -d --name alert-receiver --network ${COMPOSE_PROJECT_NAME}_dbt_airflow_network \
  --network-alias alert-receiver --user "$(id -u):0" --entrypoint python \
  -v "$PWD/scripts:/s:ro" -v "$PWD/airflow/logs:/out" \
  ${COMPOSE_PROJECT_NAME}-airflow-quality:2.7.1 /s/alert_webhook_receiver.py --output /out/webhook_received.jsonl
export DATAOPS_ALERT_WEBHOOK_URL=http://alert-receiver:9099/alert DATAOPS_ALERT_WEBHOOK_FORMAT=slack

# 2. Khởi động và kiểm tra
$DC up -d --wait airflow-scheduler
python3 scripts/health_check.py                     # phải là OVERALL: OK
$AF dags unpause dbt_transform; $AF dags unpause ge_data_quality

# 3. Một run thành công gần nhất để monitor xanh
$AF dags trigger dbt_transform --run-id demo-warmup-$(date +%H%M)
```

Mở sẵn các tab: Airflow UI (`http://localhost:8080`, Grid của `dbt_transform`), GitHub Actions,
terminal `tail -f airflow/logs/webhook_received.jsonl` (hoặc kênh Slack).

## Phần 4 — Airflow và monitoring (Thịnh, 5 phút)

| Bước | Thao tác | Điểm cần nói |
| --- | --- | --- |
| 4.1 | Airflow UI → DAGs: `dbt_transform`, `ge_data_quality`, `dataops_monitoring` | 3 DAG, 3 lịch: 06:00 hằng ngày, 6 giờ/lần, 30 phút/lần |
| 4.2 | `dbt_transform` → Graph | `check_runtime` fail nhanh khi hạ tầng hỏng; GX là cổng chặn trước docs |
| 4.3 | Grid → run gần nhất → `dbt_test` → Logs | dòng tóm tắt `202 pass` + đường dẫn bằng chứng; dòng `DATAOPS_EVENT` có cấu trúc |
| 4.4 | Terminal: `tail -3 airflow/logs/dataops_metrics/task_metrics.jsonl` | metrics mỗi task: thời gian, attempt |
| 4.5 | **Lỗi thử nghiệm**: `./scripts/dq_drill.sh setup` rồi `$AF dags trigger ge_data_quality --conf '{"schema":"dq_drill"}'` | dữ liệu Silver thật không bị đụng; ~20 s sau có alert |
| 4.6 | Mở kênh/receiver: `Data quality FAILED on dq_drill … customer_checkpoint: 9/10 … order_checkpoint: 28/30` | đúng 3 lỗi đã cấy; không retry vô ích (exit 1 = dữ liệu) |
| 4.7 | `./scripts/dq_drill.sh teardown` | dọn dẹp |

## Phần 5 — Health check và recovery (Thịnh, 5 phút)

| Bước | Thao tác | Kết quả mong đợi |
| --- | --- | --- |
| 5.1 | `$DC stop sqlserver` rồi `$AF dags trigger dbt_transform --run-id demo-outage` | — |
| 5.2 | `python3 scripts/health_check.py --skip-dbt` | `[FAIL] services sqlserver exited`, `[FAIL] sqlserver container not running`, có gợi ý lệnh |
| 5.3 | Chờ ≤ 1 phút: alert `Task retry: dbt_transform.check_runtime`; nếu monitor chạy: `DataOps health CRITICAL: services` | phát hiện trong ~1–1,5 phút |
| 5.4 | Mở [incident_runbook.md](incident_runbook.md) → bảng tra → mục 2.1 | quy trình có sẵn, không ứng biến |
| 5.5 | `$DC start sqlserver` → chờ `health_check.py` OK → clear task lỗi (UI: Clear + Downstream) | run tiếp từ chỗ dừng |
| 5.6 | `$AF dags trigger dataops_monitoring` | alert `DataOps recovered: all checks OK` |
| 5.7 | Mở [incidents/20261119-sqlserver-outage-drill.md](incidents/20261119-sqlserver-outage-drill.md) | báo cáo blameless: TTD 83 s, 5 Whys, hành động phòng ngừa |
| 5.8 | (Bảo) khôi phục phiên bản: `./scripts/rollback.sh dev backups/dev_<…> --yes` | xem [week3_deployment.md](week3_deployment.md) |

Phương án dự phòng nếu chờ retry quá lâu: dừng `ge-worker` thay vì SQL Server — `check_runtime`
fail ngay trong < 1 s mỗi attempt.

## Câu hỏi thường gặp (chuẩn bị trả lời)

| Câu hỏi | Trả lời ngắn |
| --- | --- |
| Vì sao vừa có callback vừa có monitoring DAG? | Callback chỉ chạy khi có run; monitor bắt được cả khi không có run (scheduler/service chết) và báo phục hồi |
| Làm sao tránh spam alert? | Monitor chỉ alert khi trạng thái đổi, nhắc lại sau 6 h; DAG failure do task fail không alert lần hai; GE chỉ một alert |
| Task bị timeout thì dbt trong container có chạy tiếp không? | Không: runner gắn marker và kill tiến trình trong container khi nhận SIGTERM (`dataops_timeout_drill`) |
| Webhook URL có bị lộ không? | Chỉ đọc từ env (`.env` bị gitignore), không ghi vào log/alert, lỗi gửi chỉ ghi tên exception |
| Vì sao GX lỗi không retry còn dbt run thì có? | GX exit 1 chắc chắn là dữ liệu sai; dbt trả 1 cả khi mất kết nối DB nên vẫn retry |
| Chứng minh được không? | Mỗi ngày có thư mục `docs/evidence/thinh-*` với JSON run report, alert, log |

## Sau demo

```bash
docker rm -f alert-receiver
python3 scripts/health_check.py --resolve "demo finished"
```
