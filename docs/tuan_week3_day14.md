# Tuân — tuần 3 ngày 14: lineage và tài liệu tests

Ngày rà soát: **18/11/2026**. Phạm vi theo phân công ngày 14: hoàn thiện data lineage và tài liệu các tests. Nhánh `feature/tuan-week3-day14` dựa trên `develop` sau PR #14 (`7a5ca1916954771445e2153735482eaf84879a91`). Thay đổi chỉ nằm trong tài liệu và bằng chứng rà soát.

## Tài liệu bàn giao

| Nội dung | Tài liệu | Cách kiểm tra |
| --- | --- | --- |
| Nguồn → Bronze → Silver → Gold | [Data lineage](tuan_data_lineage.md) | Đồ thị Mermaid có 6 sources đang dùng, 10 models, 15 cạnh; đối chiếu manifest và SQL `source()`/`ref()` |
| Grain, join, NULL và công thức | [Data lineage](tuan_data_lineage.md#grain-joins-và-bộ-lọc) | Đọc cả 10 model SQL; phân biệt AOV với trung bình dòng hàng, doanh thu giảm giá với số tiền giảm, giá vốn hiện tại với lịch sử |
| 202 dbt tests | [Danh mục tests](tuan_test_catalog.md) | 196 generic + 6 singular; liệt kê nhóm, phạm vi, ngưỡng, NULL, cách chọn test và đọc lỗi |
| 40 GE expectations | [Danh mục tests](tuan_test_catalog.md) | Khớp toàn bộ `rule_id` trong hai suite: customer 10, order 30 |
| Tạo/xem dbt docs | [Hướng dẫn dbt docs](tuan_week3_dbt_docs.md) | Lệnh generate, thư mục artifacts, cách đọc lineage và giới hạn của docs |
| Nguồn bằng chứng | [Evidence ngày 14](evidence/tuan-week3-day14/20261118/README.md) | Inventory từ manifest ngày 13, SHA-256, kiểm tra links và code tham chiếu |

Tài liệu lineage mô tả tự động ở cấp model/source và truy vết thủ công các cột/chỉ số quan trọng. Không tuyên bố đã tự động truy vết toàn bộ 131 cột hoặc toàn bộ quá trình ingest phía trước SQL Server.

## Kết quả và giới hạn bằng chứng

Lượt runtime tham chiếu là **`tuan-week3-day13-20261117-01`**, chạy ngày 17/11/2026: 5 tasks Airflow thành công; 10 models, 202 dbt tests, 40 GE expectations PASS; 20 kiểm tra đối chiếu và 27 ca fixture PASS. Các báo cáo chi tiết nằm tại [evidence ngày 13](evidence/tuan-week3-day13/20261117/README.md).

Ngày 14 kiểm tra sự nhất quán của tài liệu với manifest, SQL, suites và bằng chứng đã lưu. So sánh code với commit ngày 13 và 24 hashes đầu vào được chuẩn hóa LF xác nhận cùng nội dung tham chiếu; đây không phải một lượt Airflow/GE mới. CI của commit tài liệu, nếu chạy, là lần thực thi riêng và không thay thế bằng chứng tích hợp Airflow.

86/131 cột model có generic tests gắn trực tiếp; 45 cột còn lại không tự động được kết luận thiếu kiểm tra hay đúng dữ liệu. Tests tổng hợp, singular và GE có phạm vi khác nhau; không cộng số lượng để suy ra phần trăm chất lượng nghiệp vụ.

**`DQ-W2-01` vẫn OPEN**: sáu nguồn lịch sử stale theo business ModifiedDate. Tests/GE PASS và docs hoàn chỉnh không đóng vấn đề freshness. Các giới hạn đối chiếu và ca fixture giữ nguyên như [báo cáo ngày 13](tuan_week3_day13.md).

## Phần tiếp theo của Tuân

Ngày 15: **demo dbt models, tests và GE**. Dùng lineage để trình bày luồng dữ liệu, chọn một vài hợp đồng tiêu biểu từ test catalog, trình bày bằng chứng PASS và cách test phát hiện lỗi. Khi demo trực tiếp cần ghi nhận kết quả của lượt chạy thực tế; không gọi artifacts ngày 13 là kết quả vừa chạy.

README/kiến trúc/demo Airflow của Thịnh và quy trình CI/CD/deploy/rollback của Bảo thuộc phần bàn giao riêng. Hoàn thành tài liệu ngày 14 không đồng nghĩa toàn bộ checkpoint tuần 3 của nhóm đã nghiệm thu.
