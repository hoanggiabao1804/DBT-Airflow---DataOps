# Thịnh — Tuần 3, ngày 14: README, kiến trúc, hướng dẫn demo

## Sản phẩm

| File | Nội dung |
| --- | --- |
| [`README.md`](../README.md) (mới, gốc repo) | Trang đầu dự án DataOps: kiến trúc tóm tắt, khởi động nhanh, các DAG, quy trình Git/CI, vận hành/sự cố, phân công + link tài liệu từng thành viên. Giữ nguyên `1. README.md` của lab gốc |
| [`docs/architecture.md`](architecture.md) | 5 sơ đồ Mermaid: tổng quan, Bronze/Silver/Gold, các DAG, luồng observability (sequence), CI/CD; bảng nơi lưu tín hiệu; quyết định thiết kế |
| [`docs/demo_guide.md`](demo_guide.md) | Kịch bản demo 5 phần theo mục 6 kế hoạch nhóm, chi tiết lệnh + kết quả mong đợi cho phần 4–5 của Thịnh, phương án dự phòng, câu hỏi thường gặp |

## Final Acceptance — phần của Thịnh

| Tiêu chí (checkpoint tuần 3) | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Pipeline Airflow chạy thành công từ đầu đến cuối | ✅ | `thinh-week3-day13-team-e2e` 6/6 sau `deploy.sh dev` |
| Health check, alert và incident runbook hoạt động | ✅ | [thinh_week3_day11_12.md](thinh_week3_day11_12.md), [thinh_week3_day13.md](thinh_week3_day13.md) |
| Kịch bản lỗi được kiểm thử (failure/retry/alert/recovery) | ✅ | ma trận 6 kịch bản trong [thinh_week3_day13.md](thinh_week3_day13.md) |
| README, sơ đồ kiến trúc | ✅ | `README.md`, `docs/architecture.md` |
| Hướng dẫn demo | ✅ | `docs/demo_guide.md` |
| Commit/PR riêng, giải thích được phần mình | ✅ | 9 nhánh `feature/thinh-*`, mỗi ngày một tài liệu `docs/thinh_*.md` |

## Tổng kết module

**Module 4 — Monitoring**

- Structured logging `DATAOPS_EVENT` + metrics JSONL cho mọi task/DAG (`utils/logging_utils.py`, `callbacks.py`).
- Alert đa kênh, không bao giờ làm hỏng pipeline, không lộ secret (`utils/alerting.py`).
- `dataops_monitoring`: 4 nhóm check, alert theo thay đổi trạng thái, báo phục hồi.
- `ge_data_quality`: re-validation GE độc lập, metric `data_quality`, alert có chi tiết.
- SLA cho run theo lịch.

**Module 7 — Incident Response**

- Runbook 9 quy trình + phân loại SEV + bảng tra alert.
- Template báo cáo blameless + một báo cáo mẫu từ diễn tập thật.
- `scripts/health_check.py` (11 check, exit code, `--json`, `--resolve`).
- Diễn tập: dữ liệu sai, mất SQL Server, service chết, timeout, tiến trình mồ côi.

**Cải tiến pipeline (ngày 1–5, 13)**

- `check_runtime`, retry/timeout theo task, exponential backoff, `dagrun_timeout`, lịch 06:00 VN.
- Runner dọn tiến trình trong container khi task bị hủy; GX exit 1 không retry.

## Số liệu

| | |
| --- | --- |
| DAG | 4 (`dbt_transform`, `ge_data_quality`, `dataops_monitoring`, `dataops_timeout_drill`) |
| Module Python trong `airflow/dags/utils/` | 6 |
| Unit tests | 28 (chạy không cần Airflow) |
| Thời gian phát hiện lỗi hạ tầng (diễn tập) | 83 s |
| Thời gian DAG chính | ~42 s |
