# Incident: SQL Server dừng trong lúc chạy `dbt_transform` (diễn tập)

> Báo cáo mẫu điền từ [incident_template.md](../incident_template.md) cho diễn tập ngày 10
> ([thinh_week2_day10.md](../thinh_week2_day10.md)). Lỗi được tạo có chủ đích bằng
> `docker compose stop sqlserver`; mọi thời điểm và số liệu lấy từ bằng chứng thật.

| Trường | Giá trị |
| --- | --- |
| ID | INC-20261119-00 (drill) |
| Mức độ | SEV2 — pipeline dừng, dữ liệu cũ nhưng đúng |
| Trạng thái | Resolved |
| Incident commander | Thịnh |
| Bắt đầu (lỗi xảy ra) | 2026-11-19 15:58:40 (giờ VN) |
| Alert đầu tiên | 16:00:03 |
| Kết thúc (phục hồi) | 16:06:58 (alert `DataOps recovered`) |
| Thời gian phát hiện (TTD) | **83 s** (alert warning), 87 s (alert critical từ monitor) |
| Thời gian phục hồi (TTR) | ~6 phút 55 s tính từ alert đầu; ~1 phút 45 s tính từ lúc start lại SQL Server |
| Phát hiện bởi | callback retry của `dbt_transform.check_runtime` và `dataops_monitoring` |

## Tóm tắt

Container SQL Server dừng ngay trước một lần chạy `dbt_transform`. Task `check_runtime` phát hiện
`dbt debug` không kết nối được, retry 2 lần với backoff rồi fail, nên `dbt_run` không chạy và không
có bảng nào bị ghi dở. Monitor phát hiện độc lập service `sqlserver` không chạy. Sau khi start lại
SQL Server, pipeline chạy lại thành công và monitor gửi thông báo phục hồi.

## Ảnh hưởng

- DAG: `dbt_transform` run `thinh-week2-day10-infra-drill-01` failed (1 failed, 5 upstream_failed).
- Dữ liệu: Silver/Gold giữ nguyên bản của lần chạy thành công trước; không có dữ liệu sai.
- Người dùng: không (diễn tập).

## Timeline (giờ VN)

| Thời gian | Sự kiện | Nguồn bằng chứng |
| --- | --- | --- |
| 15:58:40 | SQL Server dừng; trigger `dbt_transform` | lệnh diễn tập |
| 16:00:03 | Alert **warning** `Task retry: dbt_transform.check_runtime` (attempt 1/3) | `alerts.jsonl` |
| 16:00:07 | Alert **critical** `DataOps health CRITICAL: services=sqlserver: not running` | `alerts.jsonl`, monitor run `scheduled__2026-11-19T08:30:00+00:00` |
| 16:01:49 | Attempt 2/3 fail, alert warning | `infra_drill_check_runtime_log.txt` |
| 16:04:52 | Attempt 3/3 fail → alert **critical** `Task failed: dbt_transform.check_runtime` | `alerts.jsonl` |
| 16:05:14 | Monitor vẫn CRITICAL (services + pipeline) — không gửi lại (chống spam) | `monitor_during_outage_log.txt` |
| 16:05:14 | Runbook 2.1: `docker compose start sqlserver` | lệnh |
| 16:05:31 | `dbt debug` OK trở lại | |
| 16:06:23 | `dbt_transform` `thinh-week2-day10-integrated-01` success 6/6 | `integrated_transform_run.json` |
| 16:06:52 | `ge_data_quality` success 4/4 | `integrated_ge_run.json` |
| 16:06:58 | Alert **info** `DataOps recovered: all checks OK` | `alerts.jsonl` |

Bằng chứng: [evidence/thinh-week2-day10/20261119](../evidence/thinh-week2-day10/20261119/).

## Phát hiện và chẩn đoán

- Log `check_runtime` nói thẳng nguyên nhân: `dbt debug: FAILED (target dev) - SQL Server down or
  profile invalid` / `Connection test: [ERROR]`; `Service dbt/ge-worker: running` loại trừ lỗi container.
- Alert monitor chỉ đích danh service: `services=sqlserver: not running`.
- Không cần mở log dbt hay Airflow UI để chẩn đoán.

## Nguyên nhân gốc (5 Whys)

1. Vì sao pipeline fail? — `check_runtime` không đăng nhập được SQL Server.
2. Vì sao không đăng nhập được? — container `sqlserver` đã dừng.
3. Vì sao container dừng? — dừng có chủ đích để diễn tập (trong sự cố thật: OOM, restart host, Docker update…).
4. Vì sao không tự khởi động lại? — `docker-compose.yml` không đặt `restart:` cho `sqlserver`.
5. Vì sao chưa có? — cấu hình lab gốc chưa tính tới vận hành lâu dài. **Nguyên nhân gốc**: thiếu
   chính sách tự phục hồi cho service hạ tầng.

## Xử lý

- Mitigation: start lại SQL Server theo runbook 2.1.
- Kiểm chứng: `dbt_transform` 6/6, `ge_data_quality` 4/4, monitor OK, alert `recovered`.

## Điều gì hoạt động tốt / chưa tốt

| Tốt | Chưa tốt |
| --- | --- |
| Phát hiện trong 83 s, có 2 nguồn độc lập (callback + monitor) | Retry 3 lần × ~65 s timeout kết nối kéo dài ~6 phút trước alert "Task failed" |
| `check_runtime` chặn trước khi chạm dữ liệu | SQL Server không tự restart |
| Monitor không spam khi sự cố kéo dài, có báo phục hồi | Không có đo đạc tự động TTD/TTR |

## Hành động phòng ngừa

| # | Hành động | Loại | Người phụ trách | Hạn | Issue |
| --- | --- | --- | --- | --- | --- |
| 1 | Đề xuất `restart: unless-stopped` cho `sqlserver`, `dbt`, `ge-worker` trong Compose | ngăn chặn | Bảo | tuần 3 | |
| 2 | Giới hạn `dbt debug` trong `check_runtime` ở 30 s (trước đây ~65 s khi DB chết) | phát hiện | Thịnh | ✅ ngày 13 | |
| 3 | Đưa diễn tập này vào demo cuối (kịch bản 5) | phục hồi | Thịnh | ngày 15 | |
