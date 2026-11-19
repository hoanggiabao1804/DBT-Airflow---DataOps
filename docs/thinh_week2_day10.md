# Thịnh — Tuần 2, ngày 10: kiểm thử alert thực tế và chạy pipeline tích hợp

Mục tiêu: chứng minh alert hoạt động với **lỗi thật** (không chỉ unit test), đo thời gian
phát hiện, rồi chạy toàn bộ pipeline tích hợp sau khi phục hồi. Alert được gửi qua webhook
(format Slack) tới `scripts/alert_webhook_receiver.py`; nội dung nhận được lưu trong
[webhook_received.jsonl](evidence/thinh-week2-day10/20261119/webhook_received.jsonl).

## Diễn tập 1 — Lỗi chất lượng dữ liệu (GX exit 1)

Công cụ mới `scripts/dq_drill.sh` tạo **bản sao** Silver trong schema `dq_drill` rồi cấy lỗi;
dữ liệu Silver thật không bị đụng tới.

```bash
./scripts/dq_drill.sh setup        # 25 email_promotion=9, 40 order_qty=0, 15 order_channel='Fax'
$AF dags trigger ge_data_quality --run-id thinh-week2-day10-dq-drill-01 --conf '{"schema": "dq_drill"}'
./scripts/dq_drill.sh teardown     # dọn sau khi diễn tập
```

| Kỳ vọng | Thực tế |
| --- | --- |
| customer: 1 expectation fail (`email_promotion` in set) | `customer_checkpoint: 9/10 expectations passed` |
| order: 2 expectation fail (`order_qty > 0`, `order_channel` in set) | `order_checkpoint: 28/30 expectations passed` |
| một alert critical có chi tiết | `Data quality FAILED on dq_drill — expectations failed (exit 1). customer_checkpoint: 9/10 … order_checkpoint: 28/30` |

GX phát hiện **đúng 3/3** lỗi đã cấy, không thừa không thiếu.

**Phát hiện cần sửa:** `ge_validate` đã *retry* một lần trước khi fail (thêm 1 alert warning
và ~2 phút) dù lỗi dữ liệu không bao giờ tự hết. → Sửa ở ngày 13: exit 1 của GX = fail ngay,
chỉ exit 2 (lỗi thực thi) mới retry.

## Diễn tập 2 — Mất SQL Server giữa lúc pipeline chạy

```bash
docker compose ... stop sqlserver
$AF dags trigger dbt_transform --run-id thinh-week2-day10-infra-drill-01
# … chờ hết retry …
docker compose ... start sqlserver
```

Timeline (UTC, ngày 19/11/2026) từ [alerts.jsonl](evidence/thinh-week2-day10/20261119/alerts.jsonl)
và [log check_runtime](evidence/thinh-week2-day10/20261119/infra_drill_check_runtime_log.txt):

| Giờ | Sự kiện |
| --- | --- |
| 08:58:40 | SQL Server bị dừng, trigger `dbt_transform` |
| 09:00:03 | `check_runtime` attempt 1 fail (`Connection test: [ERROR]`) → alert **warning** retry |
| 09:00:07 | `dataops_monitoring` (lịch 09:00) phát hiện `services=sqlserver: not running` → alert **critical** |
| 09:01:49 | attempt 2 fail → warning (khoảng cách ~40 s: retry_delay 30 s + jitter) |
| 09:04:52 | attempt 3 fail (khoảng cách ~2 phút: backoff ×2) → alert **critical** `Task failed: dbt_transform.check_runtime`; 5 task sau `upstream_failed` |
| 09:05:14 | monitor chạy lại: vẫn CRITICAL (services + pipeline) → **không** gửi lại alert (chống spam) |
| 09:05:14 | SQL Server được start lại |
| 09:06:23 | `dbt_transform` `thinh-week2-day10-integrated-01` success 6/6 |
| 09:06:52 | `ge_data_quality` `thinh-week2-day10-integrated-ge-01` success 4/4 |
| 09:06:58 | monitor: mọi check OK → alert **info** `DataOps recovered` |

- **Thời gian phát hiện** (lỗi → alert đầu tiên): **83 giây**; alert critical đầu tiên sau 87 giây.
- **Thời gian phục hồi** (SQL Server start → pipeline xanh + recovered): **~1 phút 45 giây**.
- Với lỗi hạ tầng, `check_runtime` dừng pipeline trước khi `dbt_run` chạm vào dữ liệu.

## Kết quả pipeline tích hợp sau phục hồi

| DAG | Run | Kết quả |
| --- | --- | --- |
| `dbt_transform` | `thinh-week2-day10-integrated-01` | 6/6 success |
| `ge_data_quality` | `thinh-week2-day10-integrated-ge-01` | 4/4 success, 40/40 expectations |
| `dataops_monitoring` | `thinh-week2-day10-monitor-after-recovery` | 5/5 success, OVERALL OK |

## Checkpoint tuần 2 (phần của Thịnh)

| Tiêu chí | Trạng thái |
| --- | --- |
| Failure của DAG tạo được log và notification | ✅ log `DATAOPS_EVENT`, metrics, alert webhook (diễn tập 2) |
| `utils/logging_utils.py`, `alerting.py`, monitoring DAG, GE integration DAG | ✅ |
| Hỗ trợ tích hợp GE | ✅ `ge_data_quality` + diễn tập dữ liệu lỗi (diễn tập 1) |

## Việc chuyển sang tuần 3

1. GX exit 1 không nên retry (diễn tập 1).
2. Log của `check_runtime` in nguyên script bash ở dòng `Running command` → khó đọc; chuyển
   thành file script.
3. Alert critical của monitor lặp lại chi tiết ở cả title và message → gọn lại.
