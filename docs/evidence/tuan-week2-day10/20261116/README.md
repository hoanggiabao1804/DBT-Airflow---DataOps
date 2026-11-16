# Bằng chứng nghiệm thu phần Tuân tuần 2 — ngày 10

Code được chạy: `ae97a1c684c2098cd1a8bd68f3fa7b58c914b15c`, sau khi PR #11 merge. Ngày **16/11/2026**, **17:03:24–17:06:35 Asia/Saigon**; JSON/logs dùng UTC.

| Thư mục/file | Nội dung | Kết quả thực tế |
| --- | --- | --- |
| `baseline/` | deps, debug, run, test; artifacts và relation map | 10 models thành công, 200 tests PASS, exit 0 |
| `freshness/` | deps, 12 timestamp tests, freshness của đúng 6 nguồn | Timestamp PASS; 6 ERROR STALE, exit 1 |
| `ge/` | Hai checkpoint trên toàn bộ customer/order Silver | 40 expectations PASS, exit 0 |
| `quality_summary.json` | Kết quả tổng hợp, test inventory, hashes cấu hình và artifacts | `overall_data_quality_status: failed_freshness` |

Artifacts được chuẩn hóa JSON UTF-8 không BOM, LF, indent 2 và sắp xếp keys; các giá trị được giữ nguyên. Stdout chỉ bỏ BOM/khoảng trắng cuối dòng. Chưa đưa connection secrets hay full dbt manifest vào evidence.

Khi tổng hợp đã kiểm tra trạng thái/mã thoát, đủ 10 models/200 tests, tập con 12 timestamp tests, 6 nguồn freshness và đủ 10+30 expectations của hai GE suites; đối chiếu exact test IDs với baseline ngày 6–7. Hash các cấu hình đã chạy được lưu để truy vết. Report JSON được tổng hợp từ artifacts lần chạy này; nó không phải output native của dbt hoặc GX.

Fixtures không chạy lại: tham chiếu [17 freshness assertions](../../tuan-week2-day6-7/20261116/contracts/summary.json) và [8 GE scenarios](../../tuan-week2-day8-9/20261116/contracts/summary.json). Đã đối chiếu SHA-256 của các định nghĩa được fixtures dùng với files hiện tại; cả hai bộ có cleanup verified. Chỉ số pass của fixtures không biến freshness trên dataset lịch sử thành PASS.

[Báo cáo chất lượng và hướng dẫn chạy lại](../../../tuan_week2_quality_report.md).
