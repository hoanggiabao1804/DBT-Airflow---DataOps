# Thịnh — Tuần 3, ngày 11–12: incident runbook, incident template, health check

Module 7 (Incident Response). Monitoring (Module 4) trả lời *"có chuyện gì không?"*;
Module 7 trả lời *"khi có chuyện thì làm gì, theo thứ tự nào, và ghi lại ra sao?"*.

## Sản phẩm

| File | Nội dung |
| --- | --- |
| [`docs/incident_runbook.md`](incident_runbook.md) | 5 phút đầu, phân loại SEV1–3, bảng tra alert → mục xử lý, 9 quy trình (hạ tầng, dbt run, lỗi dữ liệu, deps, treo/mồ côi, không chạy theo lịch, hết đĩa, rollback sau deploy, lỗi import DAG), kết thúc sự cố, phân công |
| [`docs/incident_template.md`](incident_template.md) | Mẫu báo cáo sự cố blameless: metadata, TTD/TTR, timeline, 5 Whys, hành động phòng ngừa |
| `scripts/health_check.py` | Kiểm tra toàn bộ stack bằng **một lệnh**; exit 0/1/2; `--json`; gợi ý lệnh sửa cho từng lỗi |

Mỗi alert đã có dòng `Runbook: docs/incident_runbook.md` (từ ngày 8–9), nên người nhận
alert luôn có đường dẫn tới đúng tài liệu.

## Health check

```bash
python3 scripts/health_check.py                         # bảng dễ đọc
python3 scripts/health_check.py --json > hc.json        # lưu bằng chứng / tích hợp
python3 scripts/health_check.py --skip-dbt              # nhanh hơn (~3 s)
python3 scripts/health_check.py --project thinh_dataops --airflow-url http://localhost:8090
```

| Check | Kiểm tra gì | Mức khi lỗi |
| --- | --- | --- |
| docker | Docker daemon truy cập được | FAIL (dừng các check phụ thuộc) |
| services | 6 service Compose chạy, không `unhealthy` | FAIL |
| sqlserver | `AdventureWorks2014` ở trạng thái `ONLINE` (qua `sqlcmd`) | FAIL |
| dbt | `dbt debug` trong container dbt | FAIL |
| airflow | `/health`: metadata DB + scheduler heartbeat (fallback vào trong container nếu cổng không publish) | FAIL |
| dag_imports | `airflow dags list-import-errors` rỗng | FAIL |
| last_run | run `dbt_transform` đã kết thúc gần nhất không `failed` | FAIL |
| orphans | tiến trình dbt/GX còn chạy khi không có run nào active (vấn đề Tuân bàn giao) | WARN |
| monitoring | `dataops_monitoring/latest.json` mới (< 1 h) và trạng thái của nó | theo monitor |
| alerts_24h | còn alert critical **chưa** có "recovered" sau đó | WARN |
| disk | dung lượng trống của ổ chứa repo | WARN < 5 GB, FAIL < 2 GB |

Thiết kế:

- Chỉ cần Python chuẩn + Docker CLI, chạy trên host. Container được tìm theo **label Compose**
  nên chạy được với mọi tên project.
- Mật khẩu SA truyền bằng `docker exec -e SQLCMDPASSWORD` (giá trị lấy từ biến môi trường của
  tiến trình, không nằm trên command line, không in ra). `dq_drill.sh` cũng được sửa theo cách này.
- Exit code chuẩn (0/1/2) → dùng được trong cron, CI smoke test, hoặc `&&` trong script.
- `alerts_24h` ban đầu WARN suốt 24 h sau mọi sự cố, kể cả đã phục hồi → sửa: chỉ WARN nếu
  sau alert critical cuối chưa có alert `recovered`.
- `orphans` ban đầu đếm cả shell chỉ *nhắc tới* dbt trong tham số → sửa: chỉ đếm tiến trình mà
  chương trình (token 1–2 của cmdline) là `dbt` hoặc `run_ge_checkpoints.py`.

## Kiểm chứng (19/11/2026)

| Kịch bản | Kết quả | Bằng chứng |
| --- | --- | --- |
| Stack khỏe | `OVERALL: OK`, exit 0, ~9 s | [health_check_healthy.txt](evidence/thinh-week3-day11-12/20261119/health_check_healthy.txt) |
| Dừng `ge-worker` | `[FAIL] services ge-worker exited` + gợi ý lệnh, exit 2 | [health_check_ge_worker_down.txt](evidence/thinh-week3-day11-12/20261119/health_check_ge_worker_down.txt) |
| Tiến trình dbt giả lập mồ côi | `[WARN] orphans 1 dbt/GX process(es) running but no dbt_transform run is active`, exit 1 | [health_check_orphan.txt](evidence/thinh-week3-day11-12/20261119/health_check_orphan.txt) |
| Dừng SQL Server (`--json`) | `critical`: services, sqlserver, dbt | [health_check_sqlserver_down.json](evidence/thinh-week3-day11-12/20261119/health_check_sqlserver_down.json) |

## Dùng runbook với các diễn tập đã có

| Diễn tập (ngày 10) | Alert nhận được | Mục runbook |
| --- | --- | --- |
| Mất SQL Server | `Task failed: dbt_transform.check_runtime`, `DataOps health CRITICAL: services=…` | 2.1 |
| Dữ liệu lỗi `dq_drill` | `Data quality FAILED on dq_drill` | 2.3 |

Ngày 13 sẽ chạy lại các kịch bản lỗi theo đúng runbook và điền một báo cáo sự cố mẫu.
