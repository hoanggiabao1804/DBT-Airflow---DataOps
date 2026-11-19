# Incident: <tiêu đề ngắn>

> Copy file này thành `docs/incidents/YYYYMMDD-<ten-ngan>.md` khi bắt đầu xử lý, điền dần
> trong lúc xử lý (đừng đợi xong mới viết). Viết **blameless**: mô tả hệ thống và quyết định,
> không đổ lỗi cá nhân. Quy trình: [incident_runbook.md](incident_runbook.md).

| Trường | Giá trị |
| --- | --- |
| ID | INC-YYYYMMDD-NN |
| Mức độ | SEV1 / SEV2 / SEV3 |
| Trạng thái | Investigating / Mitigated / Resolved |
| Incident commander | |
| Người tham gia | |
| Bắt đầu (phát hiện) | YYYY-MM-DD HH:MM (giờ VN) |
| Kết thúc (phục hồi) | |
| Thời gian phát hiện (TTD) | từ khi lỗi xảy ra đến khi có alert |
| Thời gian phục hồi (TTR) | từ khi có alert đến khi pipeline OK |
| Phát hiện bởi | alert `dataops_monitoring` / callback / GE / người dùng / health check |

## Tóm tắt

Hai–ba câu: chuyện gì xảy ra, ảnh hưởng gì, đã xử lý thế nào.

## Ảnh hưởng

- DAG/task bị ảnh hưởng:
- Dữ liệu: bảng nào cũ/sai, từ thời điểm nào; Gold có bị dùng khi sai không?
- Người/nhóm bị ảnh hưởng:

## Timeline (giờ VN)

| Thời gian | Sự kiện | Nguồn bằng chứng |
| --- | --- | --- |
| HH:MM | Lỗi bắt đầu (ví dụ: SQL Server dừng) | `docker compose ps`, log |
| HH:MM | Alert đầu tiên: `<title>` | `alerts.jsonl` |
| HH:MM | Xác nhận, bắt đầu xử lý; health check `FAIL services` | output `health_check.py` |
| HH:MM | Biện pháp tạm thời (pause DAG, restart service, rollback…) | lệnh đã chạy |
| HH:MM | Pipeline chạy lại thành công, alert `recovered` | run id |

## Phát hiện và chẩn đoán

- Alert/health check đã cho biết gì? Có đủ để biết ngay nguyên nhân không?
- Lệnh/log đã dùng để chẩn đoán (đường dẫn bằng chứng, run id, task, attempt).

## Nguyên nhân gốc (5 Whys)

1. Vì sao pipeline fail? —
2. Vì sao …? —
3. Vì sao …? —
4. Vì sao …? —
5. Vì sao …? — **nguyên nhân gốc**:

## Xử lý

- Biện pháp tạm thời (mitigation):
- Khắc phục triệt để (fix), PR/commit:
- Kiểm chứng sau khi xử lý (run id, health check `OK`, số dòng/tests):

## Điều gì hoạt động tốt / chưa tốt

| Tốt | Chưa tốt |
| --- | --- |
| | |

## Hành động phòng ngừa

| # | Hành động | Loại (phát hiện / ngăn chặn / phục hồi) | Người phụ trách | Hạn | Issue |
| --- | --- | --- | --- | --- | --- |
| 1 | | | | | |

## Bằng chứng

- Alert: `airflow/logs/dataops_alerts/alerts.jsonl` (các dòng liên quan)
- Báo cáo run: `scripts/airflow_run_report.py <dag> <run_id>`
- Health check: `python3 scripts/health_check.py --json`
