# Danh mục tests — dbt và Great Expectations

Tài liệu ngày 14 của Tuân, rà soát ngày **18/11/2026** theo code hiện tại. Số liệu runtime dưới đây tái sử dụng [bằng chứng ngày 13, chạy ngày 17/11/2026](evidence/tuan-week3-day13/20261117/README.md); đây không phải một lượt kiểm chứng dữ liệu mới ngày 18/11.

Pipeline có **202 dbt test nodes = 196 generic + 6 singular**, cùng **40 GE expectations** trên Silver customer/order. Lượt ngày 13 đạt 202 dbt tests và 40 GE expectations, không WARN/FAIL/ERROR/SKIP trong dbt. Các kiểm tra có thể trùng mục đích; không diễn giải thành 242 quy tắc nghiệp vụ độc lập. Xem [lineage](tuan_data_lineage.md) để xác định bảng đầu vào/đầu ra trước khi điều tra lỗi.

## 1. Mười nhóm dbt tests

Số lượng lấy từ [test_coverage.json](evidence/tuan-week3-day13/20261117/test_coverage.json), đối chiếu đủ manifest và kết quả của cùng invocation. Generic tests khai báo trong [Bronze](../dbt/models/bronze/schema.yml), [Silver](../dbt/models/silver/schema.yml), [Gold](../dbt/models/gold/schema.yml) và [sáu nguồn đang dùng](../dbt/models/bronze/src_adventureworks.yml).

| Nhóm test | Nodes | Điều kiện và giới hạn |
| --- | ---: | --- |
| `not_null` | 92 | Không được NULL; chuỗi rỗng/khoảng trắng vẫn có thể qua. |
| `unique` | 15 | Giá trị khác NULL không lặp; phải ghép `not_null` nếu khóa bắt buộc. |
| `relationships` | 15 | Khóa con khác NULL phải có trong bảng cha; không chứng minh mọi khóa cha đều xuất hiện ở bảng con. |
| `accepted_values` | 13 | Miền email `{0,1,2}`, status `{1,2,3,4,5,6}`, các cờ `{0,1}`, channel `{Online,Offline}` theo từng cột. NULL cần kiểm tra riêng. |
| `dbt_utils.accepted_range` | 2 | Discount Bronze/Silver trong `[0,1]`, gồm cả hai biên; NULL cần kiểm tra riêng. |
| `dbt_utils.unique_combination_of_columns` | 3 | Khóa dòng hàng ở source detail, Bronze và Silver. Nhóm theo toàn bộ cặp khóa; không thay cho `not_null` từng thành phần. |
| `positive_values` | 33 | Mặc định `allow_zero=true`: chấp nhận 0, loại số âm. Với `false`, yêu cầu `> 0`. Bỏ qua NULL. |
| `no_future_dates` | 21 | Timestamp khác NULL phải `<= GETUTCDATE()`, gồm cả giờ/phút/giây và được hiểu là UTC. Không đánh giá độ cũ của dữ liệu. |
| `line_total_matches` | 2 | Bronze/Silver: `line_total = order_qty × unit_price × (1 - unit_price_discount)` trong sai số tuyệt đối 0,01. Bỏ qua dòng có bất kỳ đầu vào NULL. |
| Singular đối chiếu | 6 | So tập khóa, các dòng đủ điều kiện và KPI theo từng customer/product/ngày; chi tiết mục 2. |
| **Tổng** | **202** | **196 generic + 6 singular**. |

Ba generic tests tự viết nằm tại [positive_values.sql](../dbt/tests/generic/positive_values.sql), [no_future_dates.sql](../dbt/tests/generic/no_future_dates.sql), [line_total_matches.sql](../dbt/tests/generic/line_total_matches.sql); tham số được mô tả trong [macros/schema.yml](../dbt/macros/schema.yml). Sai lệch **bằng** 0,01 vẫn qua test công thức, lớn hơn mới vi phạm; phép tính dùng decimal. Discount là phần số như `0.10`, không phải `10`; thuế/phí vận chuyển không thuộc công thức.

`order_qty` và các số đếm bắt buộc dương dùng `allow_zero=false`; giá, chi phí và doanh thu cho phép 0. Không áp `positive_values` lên profit/margin vì có thể âm. Ngày dự kiến giao và ngày bán sản phẩm được phép trong tương lai. Ship date NULL hợp lệ trước khi giao; các trường bắt buộc có `not_null` riêng.

Trong 196 generic nodes, **154 nhắm models, 42 nhắm sources**. Cả 10 models có generic tests, **86/131 cột** có generic test trực tiếp; 131 cột đều được mô tả. 45 cột còn lại có thể optional, được GE/singular kiểm tra hoặc chưa có quy tắc đầy đủ. Ví dụ Silver first/last name có GE; Gold profit/margin có đối chiếu singular. Số 86/131 không phải độ bao phủ nghiệp vụ. Dependency của một relationships test không tự làm các cột bảng cha thành “đã kiểm tra”.

## 2. Sáu singular tests đối chiếu

Cả sáu mang tags `data_quality`, `reconciliation`. SQL trả về **dòng vi phạm**; 0 dòng là đạt. Khóa NULL/trùng vẫn do các generic tests bảo vệ. Các phép FULL OUTER JOIN phát hiện cả thiếu và thừa nhóm/khóa.

| Test SQL | Đối chiếu và ý nghĩa |
| --- | --- |
| [assert_silver_customer_preservation](../dbt/tests/data_quality/assert_silver_customer_preservation.sql) | `brnz_customers.CustomerID` ↔ `slvr_customers.customer_id`: giữ nguyên tập khóa cả hai chiều, kể cả khách chưa mua hàng. Chưa đối chiếu mọi thuộc tính customer. |
| [assert_silver_product_preservation](../dbt/tests/data_quality/assert_silver_product_preservation.sql) | `brnz_products.ProductID` ↔ `slvr_products.product_id`: giữ nguyên tập khóa, kể cả sản phẩm chưa bán. Chưa đối chiếu mọi thuộc tính product. |
| [assert_silver_eligible_order_lines](../dbt/tests/data_quality/assert_silver_eligible_order_lines.sql) | Bronze với `order_qty > 0 AND unit_price >= 0` ↔ Silver theo cặp order/line. So customer/product, ba ngày, quantity/price/discount/line total, channel và discount flag; kiểm tra gross/effective price. Không dùng tổng Bronze chưa lọc làm kỳ vọng. |
| [assert_customer_metrics_reconciliation](../dbt/tests/data_quality/assert_customer_metrics_reconciliation.sql) | Silver customer + sales ↔ `gld_customer_metrics`: số đơn/đơn giảm giá, doanh thu, AOV, số lượng, ngày đầu/cuối. Gom theo đơn trước để AOV không bị lệch bởi số dòng. |
| [assert_product_metrics_reconciliation](../dbt/tests/data_quality/assert_product_metrics_reconciliation.sql) | Silver product + sales ↔ `gld_product_performance`: số đơn, lượng bán, doanh thu, giá bán trung bình, profit và margin theo từng sản phẩm. |
| [assert_daily_sales_reconciliation](../dbt/tests/data_quality/assert_daily_sales_reconciliation.sql) | Silver sales ↔ `gld_sales_summary` theo ngày: số đơn/khách/số lượng, online/offline, doanh thu, giá trị dòng trung bình và doanh thu dòng giảm giá. Kiểm tra `online_orders + offline_orders = total_orders`. |

Ngưỡng đối chiếu là **sai lệch tuyệt đối theo từng dòng/nhóm**: 0,01 cho gross, doanh thu, profit, AOV và giá trị dòng trung bình; 0,0001 cho effective unit price, average selling price và margin (đơn vị điểm phần trăm). Sai lệch đúng ngưỡng vẫn qua. Khóa, số đếm, số lượng, ngày và các trường chuyển tiếp được so chính xác với ngữ nghĩa NULL của SQL; NULL khác 0. Sai số bù trừ giữa hai ngày vẫn bị phát hiện dù tổng toàn bảng bằng nhau.

Ngày 13 bổ sung hai tests bảo toàn khóa và mở rộng ba tests Gold để kiểm tra **tám KPI**:

| Model | KPI bổ sung vào đối chiếu |
| --- | --- |
| `gld_customer_metrics` | `total_items_purchased`, `first_order_date`, `last_order_date` |
| `gld_sales_summary` | `unique_customers`, `total_items_sold`, `avg_order_line_value`, `discounted_revenue` |
| `gld_product_performance` | `avg_selling_price` |

Customer không có đơn: hai số đếm đơn bằng 0, doanh thu/AOV/số lượng/ngày đầu-cuối là NULL. Product chưa bán: số đơn và margin bằng 0, lượng/doanh thu/giá bán/profit là NULL. Product đã bán nhưng doanh thu bằng 0 có margin NULL. Profit dùng `standard_cost` hiện tại; `avg_selling_price` là trung bình giá trước discount theo dòng, không gia quyền số lượng. `avg_order_line_value` khác `avg_order_value`; không cộng số đơn theo sản phẩm để suy ra số đơn toàn kỳ.

[27 assertions fixtures](evidence/tuan-week3-day13/20261117/reconciliation_contracts.json) gồm 5 baseline, 17 thay đổi cố ý được phát hiện và 5 baseline sau rollback; cleanup đã xác nhận. [20 kiểm tra đối chiếu](evidence/tuan-week3-day13/20261117/layer_reconciliation.json) là bằng chứng bổ sung ngày 13, không cộng thêm vào 202 test nodes.

## 3. Hai checkpoint GE, đủ 40 rule IDs

[customer_checkpoint](../great_expectations/checkpoints/customer_checkpoint.yml) chạy [customer_suite](../great_expectations/expectations/customer_suite.json) trên toàn bộ `silver.slvr_customers` (10 rules); [order_checkpoint](../great_expectations/checkpoints/order_checkpoint.yml) chạy [order_suite](../great_expectations/expectations/order_suite.json) trên `silver.slvr_sales_orders` (30 rules). GE hiện không có suite cho product/Gold. Các rule dùng `meta.rule_id` ổn định để truy kết quả.

Các phép miền giá trị/ngưỡng thời gian bỏ qua NULL; rules `not_null` đảm nhiệm tính bắt buộc. Không cấu hình tỷ lệ dung sai `mostly`: giá trị được đánh giá phải đạt toàn bộ. Thời gian GE dùng tham số UTC `validation_time` do runner cấp, khác thời điểm `GETUTCDATE()` của dbt. Tên `Unknown`, chuỗi rỗng hoặc tên chưa trim không bị suite coi là lỗi định dạng.

| Customer rule ID | Điều kiện |
| --- | --- |
| `customer_columns` | Tập cột khớp chính xác 8 tên trong suite; không kiểm tra thứ tự hay kiểu dữ liệu. |
| `customer_nonempty` | Có ít nhất 1 dòng. |
| `customer_id_not_null` | `customer_id` khác NULL. |
| `customer_first_name_not_null` | `first_name` khác NULL. |
| `customer_last_name_not_null` | `last_name` khác NULL. |
| `customer_full_name_not_null` | `full_name` khác NULL; không chứng minh công thức ghép tên. |
| `customer_last_modified_date_not_null` | `last_modified_date` khác NULL. |
| `customer_id_unique` | Khóa customer không lặp. |
| `customer_email_promotion_allowed` | Giá trị khác NULL thuộc `{0,1,2}`; NULL hợp lệ khi không có Person. |
| `customer_last_modified_date_not_future` | `last_modified_date <= validation_time`. |

| Order rule ID | Điều kiện |
| --- | --- |
| `order_columns` | Tập cột khớp chính xác 20 tên trong suite; không kiểm tra thứ tự hay kiểu dữ liệu. |
| `order_nonempty` | Có ít nhất 1 dòng. |
| `order_sales_order_id_not_null` | `sales_order_id` khác NULL. |
| `order_order_detail_id_not_null` | `order_detail_id` khác NULL. |
| `order_order_date_not_null` | `order_date` khác NULL. |
| `order_due_date_not_null` | `due_date` khác NULL; được phép trong tương lai. |
| `order_status_not_null` | `status` khác NULL. |
| `order_order_channel_not_null` | `order_channel` khác NULL. |
| `order_sales_order_number_not_null` | `sales_order_number` khác NULL. |
| `order_customer_id_not_null` | `customer_id` khác NULL. |
| `order_product_id_not_null` | `product_id` khác NULL. |
| `order_order_qty_not_null` | `order_qty` khác NULL. |
| `order_unit_price_not_null` | `unit_price` khác NULL. |
| `order_unit_price_discount_not_null` | `unit_price_discount` khác NULL. |
| `order_line_total_not_null` | `line_total` khác NULL. |
| `order_gross_amount_not_null` | `gross_amount` khác NULL. |
| `order_effective_unit_price_not_null` | `effective_unit_price` khác NULL. |
| `order_has_discount_not_null` | `has_discount` khác NULL. |
| `order_key_unique` | Cặp `(sales_order_id, order_detail_id)` không lặp, `ignore_row_if=never`; một order nhiều dòng hợp lệ. |
| `order_qty_positive` | `order_qty > 0`. |
| `order_unit_price_nonnegative` | `unit_price >= 0`. |
| `order_line_total_nonnegative` | `line_total >= 0`. |
| `order_gross_amount_nonnegative` | `gross_amount >= 0`. |
| `order_effective_unit_price_nonnegative` | `effective_unit_price >= 0`. |
| `order_discount_range` | `0 <= unit_price_discount <= 1`; giảm giá 100% hợp lệ. |
| `order_status_allowed` | `status` thuộc `{1,2,3,4,5,6}`. |
| `order_channel_allowed` | `order_channel` thuộc `{Online,Offline}`. |
| `order_has_discount_allowed` | `has_discount` thuộc `{0,1}`. |
| `order_order_date_not_future` | `order_date <= validation_time`. |
| `order_ship_date_not_future` | `ship_date` NULL hoặc `<= validation_time`. |

GE xác nhận miền giá trị; dbt đảm nhiệm công thức, foreign keys và đối chiếu xuyên tầng. Bằng chứng từng rule ngày 17/11: [customer](evidence/tuan-week3-day13/20261117/production/ge/customer_checkpoint.json), [order](evidence/tuan-week3-day13/20261117/production/ge/order_checkpoint.json), [summary](evidence/tuan-week3-day13/20261117/production/ge/summary.json).

## 4. Chọn và chạy lại đúng phạm vi

Chạy PowerShell tại gốc repository sau khi dựng [runtime Airflow](tuan_week3_day11_12.md). SQL Server đã restore, service `dbt` đang chạy và models đã build. Không chạy đồng thời với DAG/fixtures khác. Ví dụ dưới đây tạo đường dẫn artifacts mới và xem danh sách trước khi chạy sáu tests đối chiếu:

```powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$dbtTarget = "target/manual-tests-$stamp"
docker compose exec -T -e DBT_TARGET_PATH=$dbtTarget -e DBT_LOG_PATH="$dbtTarget/logs" dbt dbt ls --target dev --resource-type test --select tag:reconciliation
if ($LASTEXITCODE -ne 0) { throw 'Cannot list reconciliation tests' }
docker compose exec -T -e DBT_TARGET_PATH=$dbtTarget -e DBT_LOG_PATH="$dbtTarget/logs" dbt dbt test --target dev --select tag:reconciliation
if ($LASTEXITCODE -ne 0) { throw 'Inspect dbt run_results.json and logs' }
```

Danh sách phải có đúng sáu tên ở mục 2. Các cách chọn khác: thay cùng selector trong cả `dbt ls --resource-type test` và `dbt test`; bỏ `--select` ở cả hai để kiểm tra toàn bộ 202 nodes. Không đổi selector giữa bước xem và bước chạy.

| Mục đích | Selector | Phạm vi kỳ vọng hiện tại |
| --- | --- | --- |
| Đối chiếu xuyên tầng | `--select tag:reconciliation` | 6 singular tests. |
| Timestamp nguồn | `--select tag:source_timestamp` | 12 tests `not_null`/`no_future_dates`, đã nằm trong 202. |
| Điều tra một phép đối chiếu | `--select assert_daily_sales_reconciliation` | 1 singular test; cần các bảng đầu vào đã tồn tại. |
| Toàn bộ dbt tests | Bỏ `--select` | 202 nodes; không tự build models hay chạy GE/freshness. |

Chọn một model hoặc dùng dấu `+` có thể kéo theo tests qua cơ chế chọn gián tiếp; luôn đọc kết quả `dbt ls`. Một test tham chiếu bảng cha không chứng minh đã chạy tất cả tests của bảng cha. Muốn nghiệm thu toàn pipeline, dùng DAG `dbt_transform` theo [ngày 11–12](tuan_week3_day11_12.md), không suy từ một lượt chọn hẹp.

Chạy riêng cả hai checkpoint GE bằng service của overlay Airflow:

```powershell
$geStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T ge-worker python /workspace/scripts/run_ge_checkpoints.py --target dev --schema silver --output-dir "/evidence/manual-ge-$geStamp"
$geExit = $LASTEXITCODE
Write-Host "GE exit code: $geExit"
```

Đọc `great_expectations/uncommitted/manual-ge-<stamp>/summary.json` và hai checkpoint JSON. Thêm `--checkpoint customer_checkpoint` hoặc `--checkpoint order_checkpoint` nếu chỉ điều tra một suite; kết quả đó không thay cho cả 40 rules. `--schema` là schema vật lý của Silver. Xem [GE README](../great_expectations/README.md) cho cách chạy container độc lập và fixtures; [ngày 13](tuan_week3_day13.md) có lệnh tạo lại báo cáo coverage/đối chiếu.

## 5. Đọc lỗi và tách freshness

dbt CLI trả 0 khi lệnh hoàn tất thành công, 1 khi có lỗi được xử lý (bao gồm test FAIL), 2 khi lỗi chưa được xử lý. Không chỉ dựa exit code: đọc `status`, `failures`, `message`, `unique_id` trong `run_results.json`; `warn` không phải PASS. `dbt ls` thành công chỉ xác nhận danh sách, không xác nhận dữ liệu đạt.

GE runner và các runner báo cáo ngày 13 dùng **0 = đạt, 1 = có vi phạm, 2 = lỗi input/cấu hình/thực thi**. Airflow lưu `native_exit_code` và `exit_code` trong `task_summary.json`; GE exit 1/2 làm task thất bại và chặn `dbt_docs` qua `all_success`. Artifact thiếu hoặc không nhất quán cũng có thể khiến wrapper trả 2 dù lệnh con trả 0.

1. Xác định đúng DAG run/task/attempt, target và schema; đọc artifact của chính lượt đó, tránh nhầm output cũ. Manifest và run results dùng cho coverage phải cùng invocation.
2. Với dbt FAIL, dùng `unique_id` tìm test SQL hoặc khai báo YAML tương ứng. So grain, trường bắt buộc, ngưỡng và NULL theo các bảng trên; với singular, xem nhóm/khóa lệch trước khi xét tổng toàn bảng.
3. Với GE FAIL, tìm `rule_id`, `unexpected_count` hoặc `observed_value` trong checkpoint JSON. Missing table/connection/output trùng thuộc lỗi thực thi, không phải dữ liệu vi phạm một rule.
4. Sửa nguyên nhân, chạy lại selector liên quan, sau đó kiểm chứng đầy đủ phạm vi cần bàn giao. Giữ lại evidence cũ và output mới riêng; không đổi ngưỡng hoặc thêm bỏ qua lỗi chỉ để pipeline xanh.

**Freshness `DQ-W2-01` vẫn mở.** Lệnh `dbt source freshness --target dev` chạy riêng, dùng `MAX(ModifiedDate)` và giờ UTC; ngưỡng demo cảnh báo 24 giờ/lỗi 48 giờ. Đây là thời điểm thay đổi nghiệp vụ, không phải ingestion/restore time. Sáu nguồn AdventureWorks lịch sử đã quá hạn theo [báo cáo tuần 2](tuan_week2_quality_report.md); ngày 13 và đợt tài liệu ngày 14 không chạy lại freshness. `no_future_dates` PASS không chứng minh dữ liệu mới, 12 source timestamp tests không phải sáu freshness checks, và DAG thành công không đóng finding này.
