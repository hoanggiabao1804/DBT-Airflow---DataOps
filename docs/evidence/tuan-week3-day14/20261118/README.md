# Bằng chứng rà soát tài liệu — Tuân ngày 14

Ngày **18/11/2026**; loại bằng chứng: **kiểm tra tài liệu**, tham chiếu runtime ngày **17/11/2026**. Không chạy lại Airflow/GE trong đợt rà soát này.

| File | Mục đích |
| --- | --- |
| [lineage_inventory.json](lineage_inventory.json) | 6 nguồn đang dùng, 7 khai báo không dùng, 10 models, 15 cạnh dependency; relations, đường dẫn code, thống kê test, hash manifest gốc |
| [documentation_review.json](documentation_review.json) | Kết quả đối chiếu Mermaid/manifest/SQL, test và GE rule IDs, links nội bộ, hashes tài liệu và code tham chiếu |
| [Evidence ngày 13](../../tuan-week3-day13/20261117/README.md) | Kết quả runtime gốc: 5 tasks, 10 models, 202 dbt tests, 40 GE expectations, 20 đối chiếu, 27 fixtures |

Manifest dùng để lập inventory là artifact `dbt_test` của run `tuan-week3-day13-20261117-01`, invocation `873993fc-a1e3-4db2-b8be-c0b5b56cd9bf`, SHA-256 `97c58137678c6accd5a4396a47c25a9cf39645fcc60a5ec089fc163b9aa122dc`. Manifest đầy đủ nằm trong thư mục local ignored `great_expectations/uncommitted/airflow/`; JSON tóm tắt được commit để review mà không đưa toàn bộ target vào Git. Nếu máy mới không có artifact gốc, có thể đối chiếu SQL/YAML và các báo cáo ngày 13 đã commit; manifest tạo lại có invocation/hash mới, không được gắn nhãn là artifact cũ.

Hash nội dung text trong báo cáo dùng UTF-8 với newline LF để kết quả không phụ thuộc CRLF của Windows. Hash manifest gốc dùng bytes nguyên trạng. Code hiện tại được so sánh với commit ngày 13 `315fcdd0fe8e504d385625b6734143e572014ea7`; toàn bộ các thư mục thực thi được kiểm tra bằng Git, đồng thời 24 file có hashes trong provenance ngày 13 được đối chiếu riêng.

Các con số test là inventory và kết quả của lượt tham chiếu, không chứng minh mọi quy tắc nghiệp vụ đã có test. Bảy sources `raw` không dùng không được tính vào sáu nguồn hoạt động; `brnz_example` vẫn là model đang build nhưng không có model downstream. `DQ-W2-01` giữ trạng thái **OPEN**. Xem [bàn giao ngày 14](../../../tuan_week3_day14.md) và [lineage](../../../tuan_data_lineage.md).
