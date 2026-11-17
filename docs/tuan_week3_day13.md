# Tuân — tuần 3, ngày 13: đối chiếu dữ liệu và test coverage

Phạm vi theo `Project-Devops.md`: kiểm tra số liệu Bronze → Silver → Gold và độ bao phủ tests trong pipeline tích hợp. Ngày 13 tiếp nối [ngày 11–12](tuan_week3_day11_12.md), sau khi PR #13 đã merge vào `develop`. Models, quy tắc GE, cấu hình Airflow và freshness giữ nguyên.

## Kết quả nghiệm thu ngày 17/11/2026

**Hoàn thành phạm vi ngày 13 của Tuân.** Lượt Airflow `tuan-week3-day13-20261117-01` chạy bằng scheduler/LocalExecutor từ **14:27:15 đến 14:32:13 giờ Việt Nam**; cả năm tasks thành công lần đầu. Kết quả: **10 models, 202 dbt tests, 40 GE expectations PASS**, docs generate thành công.

Lượt đọc đối chiếu sau DAG, **14:32:35–14:32:38**, đạt **20/20 kiểm tra**, gồm sáu SQL đối chiếu đều trả về 0 vi phạm. 27/27 trường hợp fixtures đã đạt, trong đó 17 thay đổi cố ý đều được phát hiện đúng; rollback và cleanup được xác nhận.

| Số liệu | Bronze | Silver | Gold |
| --- | ---: | ---: | ---: |
| Khách hàng | 19.820 | 19.820 | 19.820 customer metrics |
| Sản phẩm | 504 | 504 | 504 product performance |
| Dòng hàng | 121.317 đủ điều kiện, 0 bị lọc | 121.317 | 1.124 dòng tổng hợp theo ngày |
| Đơn hàng phân biệt | 31.465 | 31.465 | Tổng theo customer/daily: 31.465 |
| Số lượng bán | 274.914 | 274.914 | Mỗi bảng Gold cộng về 274.914 |
| Doanh thu thuần, giá trị decimal gốc | `109846381.399888` | `109846381.399888` | Cả ba bảng: `109846381.399888` |

Gold vẫn giữ **701 khách hàng và 238 sản phẩm chưa có giao dịch**, với quy tắc NULL/0 theo model. `brnz_example` có 19.820 dòng và không nằm trên nhánh tổng hợp sales. Tổng `total_orders` của product là 121.317 trong dataset này; đây là tổng theo sản phẩm, **không phải** 121.317 đơn hàng phân biệt.

Bằng chứng: [chỉ mục nghiệm thu](evidence/tuan-week3-day13/20261117/README.md), [đối chiếu số liệu](evidence/tuan-week3-day13/20261117/layer_reconciliation.json), [test coverage](evidence/tuan-week3-day13/20261117/test_coverage.json), [27 trường hợp fixtures](evidence/tuan-week3-day13/20261117/reconciliation_contracts.json). Các kiểm tra tổng hợp là bằng chứng bổ sung trên cùng dữ liệu, không được cộng vào 202 dbt test nodes.

## Khoảng trống đã bổ sung

Hai tests mới kiểm tra tập khóa khách hàng và sản phẩm theo cả hai chiều Bronze ↔ Silver. Quan hệ khóa ngoại hiện có chỉ chứng minh khóa Silver tồn tại trong Bronze; nó không phát hiện một khách hàng/sản phẩm chưa có giao dịch bị mất khỏi Silver. So sánh tập khóa phát hiện cả trường hợp xóa một khóa rồi thêm khóa khác khiến số dòng vẫn bằng nhau. Kiểm tra `not_null`/`unique` hiện có tiếp tục bảo vệ tính duy nhất của khóa.

Ba tests đối chiếu Gold được mở rộng để kiểm tra tám chỉ số trước đây chỉ có kiểm tra miền giá trị hoặc timestamp:

| Test | Chỉ số bổ sung |
| --- | --- |
| `assert_customer_metrics_reconciliation` | `total_items_purchased`, `first_order_date`, `last_order_date` |
| `assert_daily_sales_reconciliation` | `unique_customers`, `total_items_sold`, `avg_order_line_value`, `discounted_revenue` |
| `assert_product_metrics_reconciliation` | `avg_selling_price` |

Tests đối chiếu theo từng khách hàng/sản phẩm/ngày, giữ nguyên ý nghĩa NULL cho đối tượng không có giao dịch. Sai lệch doanh thu một nhóm tăng và nhóm khác giảm vẫn bị phát hiện, dù tổng toàn bảng không đổi. Ngưỡng tiền là 0,01; giá bán trung bình và tỷ lệ margin dùng 0,0001. Đây là ngưỡng tuyệt đối trên từng nhóm, không phải phần trăm sai lệch doanh thu.

## Đọc số liệu đúng theo cấp dữ liệu

- Customer và product không có bộ lọc dòng khi chuyển Bronze → Silver; tập khóa phải được giữ đầy đủ.
- Sales Bronze lấy header LEFT JOIN detail. Silver chỉ giữ `order_qty > 0 AND unit_price >= 0`; NULL cũng bị loại theo ngữ nghĩa SQL. Do đó đối chiếu Silver với **Bronze đủ điều kiện**, đồng thời báo riêng số dòng bị lọc.
- Một dòng sales là một **order line**, khóa `(sales_order_id, order_detail_id)`. Số đơn hàng là `COUNT(DISTINCT sales_order_id)`.
- Doanh thu dùng `line_total` sau discount, chưa gồm thuế/phí vận chuyển; không so trực tiếp với `SalesOrderHeader.TotalDue`.
- `avg_order_value` ở customer dùng doanh thu/đơn hàng; `avg_order_line_value` ở daily dùng doanh thu/dòng hàng. `avg_selling_price` ở product là trung bình giá trước discount theo dòng, không gia quyền theo số lượng.
- Không cộng số đơn của từng sản phẩm để suy ra tổng số đơn: một đơn có thể mua nhiều sản phẩm. Tương tự, số khách phân biệt từng ngày không cộng thành số khách phân biệt toàn kỳ.
- Profit là ước tính theo `standard_cost` hiện tại; margin NULL khi có bán nhưng doanh thu bằng 0. Đây không phải lợi nhuận kế toán theo giá vốn lịch sử.

## Báo cáo có thể chạy lại

`scripts/reconcile_dbt_layers.py` đọc manifest và `run_results.json` của **cùng lần `dbt test`**, xác nhận toàn bộ test nodes đã chạy PASS đúng một lần và SQL khớp file hiện tại. Sau đó nó đọc số dòng nguồn/models, số lượng, doanh thu, số đơn, nhóm bị lọc và thực thi lại sáu câu SQL đối chiếu để đếm vi phạm. Các truy vấn nằm trong một transaction `SERIALIZABLE`; không sửa dữ liệu nguồn hoặc models. Transaction này bắt đầu sau dbt, không phải snapshot chung với lượt build/test trước đó.

`scripts/report_dbt_test_coverage.py` chỉ đọc artifacts, phân biệt target thật sự của generic test với bảng cha được tham chiếu trong relationships. Nó ghi nhận test thiếu/thừa/trùng, trạng thái không PASS và khác invocation là lỗi. Singular test có nhiều dependencies được liệt kê riêng; không tự suy diễn mọi cột trong dependency đã được kiểm tra nghiệp vụ.

`scripts/verify_dbt_reconciliation_contracts.py` dùng bảng tạm theo connection, chạy đúng SQL test hiện tại với dữ liệu hợp lệ và 17 thay đổi cố ý. Mỗi thay đổi được rollback; cuối cùng chạy lại baseline và xác nhận bảng tạm được xóa. Các trường hợp gồm mất/thừa/thay khóa cùng số dòng, tám KPI sai, NULL bị đổi thành 0 ở đối tượng chưa có giao dịch, và doanh thu sai bù trừ giữa hai ngày.

## Độ bao phủ tests

Manifest và kết quả ngày 13 có đúng **202 test nodes**, gồm **196 generic + 6 singular**; 202 kết quả PASS, không thiếu/thừa/trùng IDs. Hai IDs mới là hai tests bảo toàn tập khóa; không xóa test nào trong baseline 200 của ngày 11–12. Việc giữ ID không có nghĩa SQL không đổi: ba singular tests Gold đã được mở rộng như trên.

| Model | Cột được mô tả | Cột có generic test trực tiếp |
| --- | ---: | ---: |
| `brnz_customers` | 7 | 3 |
| `brnz_example` | 4 | 4 |
| `brnz_products` | 26 | 11 |
| `brnz_sales_orders` | 17 | 14 |
| `slvr_customers` | 8 | 4 |
| `slvr_products` | 18 | 9 |
| `slvr_sales_orders` | 20 | 17 |
| `gld_customer_metrics` | 10 | 8 |
| `gld_product_performance` | 12 | 7 |
| `gld_sales_summary` | 9 | 9 |
| **Tổng** | **131** | **86** |

Cả 10 models có generic tests. Trong 196 generic tests có 154 tests nhắm models và 42 tests nhắm sources; báo cáo phân biệt 6 nguồn được models dùng với 7 khai báo nguồn legacy chưa dùng. 12 timestamp tests là một phần của 202, không cộng thêm. GE có 40 expectations riêng và trùng mục đích với một số dbt tests; không cộng thành 242 quy tắc độc lập.

**45 cột không có generic test trực tiếp không đồng nghĩa 45 lỗi.** Ví dụ, Silver `first_name`/`last_name` đã có GE kiểm tra không NULL; Gold `total_profit`/`profit_margin_pct` đã có đối chiếu singular. Các cột optional như `purchase_order_number`, `sales_person_id`, `territory_id`, thuộc tính sản phẩm như `class`/`style`/`size` và các trường mô tả còn giới hạn về quy tắc giá trị/mapping. Đã công khai danh sách từng cột trong báo cáo máy đọc được; không thêm `not_null` đại trà để làm tăng tỷ lệ. Các tests ngày 13 tăng khả năng phát hiện thiếu dữ liệu và sai KPI dù chỉ số generic-column vẫn là 86/131.

## Cách chạy

Khởi động runtime theo hướng dẫn ngày 11–12, trigger một lượt DAG mới và đợi đủ năm tasks `success`. Không chạy song song với dbt/fixture khác. Lấy thư mục attempt `dbt_test` của chính lượt đó; không dùng manifest từ task `dbt_docs` vì khác invocation.

```powershell
$runId = 'tuan-day13-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T airflow-scheduler airflow dags trigger dbt_transform --run-id $runId
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T airflow-scheduler airflow tasks states-for-dag-run dbt_transform $runId

# Sau khi năm tasks success, điền đường dẫn attempt thực tế của dbt_test:
$attemptRelative = 'airflow/<run-hash>/dbt_test/try-<n>-<uuid>'
$attempt = "great_expectations/uncommitted/$attemptRelative"
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T ge-worker python /workspace/scripts/reconcile_dbt_layers.py --manifest "/evidence/$attemptRelative/manifest.json" --run-results "/evidence/$attemptRelative/run_results.json" --target dev --output-dir "/evidence/day13-reconciliation-$stamp"
python scripts/report_dbt_test_coverage.py --manifest "$attempt/manifest.json" --run-results "$attempt/run_results.json" --baseline-results docs/evidence/tuan-week3-day11-12/20261117/production/dbt_test.run_results.json --output "great_expectations/uncommitted/day13-coverage-$stamp.json"
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T ge-worker python /workspace/scripts/verify_dbt_reconciliation_contracts.py --project-dir /workspace/dbt --output "/evidence/day13-contracts-$stamp.json"
```

Kiểm tra exit code từng lệnh: `0` đạt, `1` có vi phạm, `2` lỗi thực thi/input. Coverage runner trên host chỉ cần Python standard library; hai runner SQL dùng môi trường `ge-worker` đã có pyodbc/SQLAlchemy. Fixture verifier dùng SQL-auth target mặc định trong profile local; nếu đổi target cần đồng bộ profile trước khi chạy. Không tái sử dụng đường dẫn output đã tồn tại.

## Giới hạn và bàn giao

Tỷ lệ tests PASS không phải tỷ lệ bao phủ nghiệp vụ. Số cột có generic test trực tiếp cũng không tính đầy đủ GE, kiểm tra khóa ghép hay singular tests. Các trường mô tả/nullable có thể không có generic test trực tiếp; tests bảo toàn khóa mới không khẳng định mọi phép đổi tên, thay NULL hoặc thuộc tính dimension đã được đối chiếu. Source inventory chỉ là thông tin số dòng; nó không thay cho kiểm toán đầy đủ từng giá trị hệ thống nguồn → Bronze.

GE tiếp tục chỉ áp dụng Silver customer/order. Freshness không chạy lại trong ngày 13; phát hiện `DQ-W2-01` của sáu nguồn lịch sử vẫn mở. Failure/retry/alert của scheduler và E2E chung thuộc phần phối hợp với Thịnh; deploy/rollback thuộc Bảo. Ngày 14 của Tuân là hoàn thiện data lineage và tài liệu tests; ngày 15 là demo.
