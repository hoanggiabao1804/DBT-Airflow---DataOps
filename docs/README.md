# Tài liệu DataOps

## Danh sách thành viên nhóm

| MSSV     | Họ và tên        |
| -------- | ---------------- |
| 23120022 | Hoàng Gia Bảo    |
| 23120168 | Trần Quốc Thịnh  |
| 23120389 | Nguyễn Ngọc Tuân |

Bộ tài liệu này đáp ứng mục **Documentation** trong
[DataOps Project Requirements](../4.%20DATAOPS_PROJECT_REQUIREMENTS.md#documentation).
Tất cả lệnh bên dưới chạy từ thư mục gốc repository, trừ khi có ghi khác.

| Yêu cầu                             | Tài liệu                                                                                            |
| ----------------------------------- | --------------------------------------------------------------------------------------------------- |
| Architecture diagram (PDF hoặc ảnh) | [Sơ đồ PDF](architecture.pdf), [ảnh PNG](architecture.png), [giải thích kiến trúc](architecture.md) |
| Setup guide (Markdown)              | [Cài đặt và chạy thử](setup.md)                                                                     |
| API/Model documentation             | [Giao diện các dbt models](model_reference.md); project không cung cấp HTTP API                     |
| Troubleshooting guide               | [Chẩn đoán và xử lý lỗi](troubleshooting.md)                                                        |

Các tài liệu chuyên sâu đã có: [data lineage](tuan_data_lineage.md),
[test catalog](tuan_test_catalog.md), [dbt docs](tuan_week3_dbt_docs.md),
[GE checkpoints](../great_expectations/README.md) và
[deploy/rollback](week3_deployment.md). Chúng bổ sung chi tiết kiểm thử,
không thay thế các bước setup cơ bản ở đây.

**Phạm vi được mô tả:** code hiện có trên nhánh đang đọc tài liệu. DAG
`dbt_transform` mặc định paused/chạy thủ công. Sáu nguồn AdventureWorks2014
lịch sử vượt ngưỡng freshness 24/48 giờ; đây là phát hiện dữ liệu đã biết,
không phải lỗi kết nối hoặc bằng chứng pipeline tự động đã đạt SLA.
