# Bằng chứng Tuân — Tuần 2, ngày 6–7

Ngày 16/11/2026, Asia/Saigon. Timestamp trong JSON/logs là UTC. [Báo cáo và cách chạy lại](../../../tuan_week2_day6_7.md).

| Thư mục | Kết quả và ý nghĩa |
| --- | --- |
| [baseline](baseline/baseline_status.json) | dbt debug/run/test thành công: 10 models, 200 tests PASS, gồm 12 tests timestamp mới. |
| [freshness-final](freshness-final/freshness_status.json) | Lần chạy nghiệm thu dùng macro UTC: 12 timestamp tests PASS; 6 sources ERROR STALE; runner giữ exit 1. |
| [contracts](contracts/summary.json) | 17 assertions đúng: 3 lần freshness kiểm tra statuses/exit codes; 14 timestamp tests với 3 FAIL cố ý. Cleanup schema xác nhận thành công. |
| [freshness](freshness/freshness_status.json) | Lần khảo sát đầu trước macro UTC: 12 tests PASS, 6 nguồn stale. Dùng kết quả final để nghiệm thu mã cuối. |
| [freshness-utc](freshness-utc/freshness_status.json) | Lần thử bị lỗi ở `dbt deps` do chạy đồng thời với baseline trên cùng thư mục packages. Status failed, exit 2; không phải kết quả freshness. Đã chạy lại tuần tự ở `freshness-final`. |

Nguồn được kiểm tra: Sales.Customer, Sales.SalesOrderHeader, Sales.SalesOrderDetail, Production.Product, Production.ProductSubcategory, Person.Person. Dữ liệu lịch sử 2008–2015 không đáp ứng ngưỡng demo 24h WARN / 48h ERROR; không có lỗi SQL trong lần freshness nghiệm thu.

`sources.json` chứa watermark, thời điểm kiểm tra, tuổi dữ liệu và tiêu chí của từng nguồn. Source YAML và macro được ghi hash trong summaries. 200 tests PASS chỉ xác nhận các quy tắc data tests, không biến nguồn stale thành fresh.

Fixtures chỉ tạo các views trong schema riêng. FAIL ở `timestamp_tests` và ERROR ở `all_sources` là dữ liệu cố ý sai để xác minh khả năng phát hiện; đọc `contracts/summary.json` để thấy trạng thái tổng hợp passed và cleanup_verified true.

JSON/text evidence được chuẩn hóa UTF-8 không BOM, LF, JSON indent 2/sắp xếp keys và bỏ khoảng trắng cuối dòng log. Giá trị kết quả, timestamp và nội dung thông báo giữ nguyên. Không lưu profile/credentials hoặc full manifest.
