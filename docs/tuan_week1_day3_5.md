# Tuân — Ngày 3–5, tuần 1

Ngày thực hiện: **07/11/2026**, múi giờ Asia/Saigon. Nhánh: `feature/tuan-week1-day3-5`, tách từ `develop` sau khi PR ngày 1–2 đã được merge.

Phần này thực hiện công việc của Tuân trong kế hoạch local `Project-Devops.md`: ngày 3–4 bổ sung schema tests, relationship tests và 3 generic tests; ngày 5 chạy kiểm thử, sửa lỗi model và lưu bằng chứng. [Báo cáo ngày 1–2](tuan_week1_day1_2.md) được giữ làm mốc trước thay đổi.

## Kết quả kiểm chứng

**Đã hoàn thành phần ngày 3–5 của Tuân:** 10/10 models chạy thành công, **188/188 tests PASS**, cả 3 Gold models đúng trên dữ liệu kiểm thử và 8/8 trường hợp kiểm thử generic macros khớp kỳ vọng. Baseline chạy từ **16:27:39 đến 16:31:10 ngày 07/11/2026** (Asia/Saigon).

| Kiểm tra | Kết quả / bằng chứng |
| --- | --- |
| Trước sửa: 4 tests đối chiếu dữ liệu | 2 PASS, 2 FAIL: sales summary sai ở 421 ngày; customer metrics sai ở 15.913 khách hàng. Đây là số dòng không khớp của từng test, không phải số lần một KPI sai. [Kết quả](evidence/tuan-week1-day3-5/20261107/reconciliation.before.run_results.json). |
| Trước sửa: chạy SQL Gold với dữ liệu kiểm thử | Cả 3 models bị phát hiện lỗi: AOV/số đơn giảm giá, số đơn online và chia cho 0 khi tính margin. [Kết quả](evidence/tuan-week1-day3-5/20261107/gold_contracts.before.json). |
| Sau sửa: `dbt deps`, `dbt debug`, `dbt run`, `dbt test` | Cả 4 lệnh exit 0; **10/10 models thành công**, **188/188 tests PASS**, không FAIL/ERROR/WARN/SKIP. Cả 4 singular tests đối chiếu đều có 0 dòng sai lệch. [Trạng thái](evidence/tuan-week1-day3-5/20261107/baseline/baseline_status.json), [run](evidence/tuan-week1-day3-5/20261107/baseline/run.run_results.json), [test](evidence/tuan-week1-day3-5/20261107/baseline/test.run_results.json). |
| Kiểm thử 3 generic macros bằng dữ liệu hợp lệ và dữ liệu cố tình sai | **8/8 trường hợp khớp kỳ vọng**: 4 PASS, 4 FAIL đúng chủ đích với số dòng lỗi 2/3/2/3; `contracts_verified` và `cleanup_verified` đều true, trạng thái tổng hợp passed. [Kết quả](evidence/tuan-week1-day3-5/20261107/generic_contracts/summary.json). |
| Sau sửa: chạy SQL Gold với dữ liệu kiểm thử | **3/3 models PASS**, không có mismatch, gồm cả trường hợp doanh thu bằng 0. [Kết quả](evidence/tuan-week1-day3-5/20261107/gold_contracts.after.json). |

[Thư mục bằng chứng](evidence/tuan-week1-day3-5/20261107/README.md) phân biệt rõ lần chạy trước sửa, sau sửa và các lỗi cố tình tạo để kiểm tra khả năng phát hiện của tests.

## Tests được bổ sung

Schema được mô tả cho đủ **10 models**: 4 Bronze, 3 Silver, 3 Gold. Khóa dòng hàng là cặp `(sales_order_id, order_detail_id)`; riêng `sales_order_id` có thể lặp vì một đơn có nhiều dòng.

Project khai báo **13 source tables**; phạm vi kiểm thử nguồn trong lần này là **6 bảng được các models sử dụng**. Bảy source declarations chưa dùng vẫn được giữ nguyên và không được tính là đã có test coverage.

| Phạm vi | Nội dung |
| --- | --- |
| [Bronze](../dbt/models/bronze/schema.yml) | Khóa và NULL, giá/chi phí/số lượng, miền giá trị status/flag/discount, ngày thực tế; relationships từ orders đến customers/products. Tests kiểm tra dữ liệu chưa lọc, kể cả các dòng bị Silver loại bỏ. |
| [Silver](../dbt/models/silver/schema.yml) | Khóa, relationships orders → dimensions và dimensions → Bronze; giá trị được chuẩn hóa, trường phát sinh và công thức dòng hàng. |
| [Gold](../dbt/models/gold/schema.yml) | Khóa, relationships → Silver, ngày và các giá trị không âm phù hợp; mô tả rõ NULL/0 và ý nghĩa KPI. Lợi nhuận và biên lợi nhuận có thể âm nên không bị ép phải dương. |
| [6 bảng nguồn đang dùng](../dbt/models/bronze/src_adventureworks.yml) | Khóa nguồn và quan hệ giữa `Customer`, `Person`, `Product`, `ProductSubcategory`, `SalesOrderHeader`, `SalesOrderDetail`; giữ các foreign key tùy chọn có thể NULL. |

Ba generic macros mới có thể tái sử dụng trong YAML:

| Macro | Quy tắc |
| --- | --- |
| [`positive_values`](../dbt/tests/generic/positive_values.sql) | Mặc định cho phép 0 (`allow_zero: true`); dùng `allow_zero: false` cho số lượng phải lớn hơn 0. Giá và chi phí bằng 0 vẫn hợp lệ. |
| [`no_future_dates`](../dbt/tests/generic/no_future_dates.sql) | Không cho timestamp thực tế vượt thời điểm `GETUTCDATE()`. Dự án hiện diễn giải các timestamp không kèm múi giờ là UTC. |
| [`line_total_matches`](../dbt/tests/generic/line_total_matches.sql) | Kiểm tra `line_total = order_qty × unit_price × (1 − unit_price_discount)`; sai lệch tuyệt đối tối đa **0,01**. Áp dụng cho Bronze và Silver. |

Các generic macros bỏ qua NULL để kết hợp với `not_null` theo từng cột. Không áp dụng `no_future_dates` cho ngày dự kiến như `due_date`, `sell_start_date`, `sell_end_date`; `ship_date` được phép NULL khi chưa giao hàng. Không có cột địa chỉ email trong luồng models hiện tại, vì vậy generic thứ ba kiểm tra công thức dòng hàng thay vì thêm một email test không có dữ liệu để áp dụng.

Bốn singular tests trong [`dbt/tests/data_quality`](../dbt/tests/data_quality) kiểm tra kết quả nghiệp vụ:

- `assert_silver_eligible_order_lines`: đối chiếu dòng Bronze có `order_qty > 0` và `unit_price >= 0` với Silver, phát hiện thiếu/thừa dòng, sai trường giữ lại hoặc sai trường tính toán.
- `assert_daily_sales_reconciliation`: đối chiếu KPI theo ngày, đếm đơn riêng biệt theo kênh và kiểm tra tổng đơn online + offline.
- `assert_customer_metrics_reconciliation`: tổng hợp độc lập theo đơn trước khi tính AOV, kiểm tra doanh thu/số đơn/số đơn có giảm giá của từng khách hàng, kể cả khách chưa có đơn.
- `assert_product_metrics_reconciliation`: đối chiếu theo từng sản phẩm, kiểm tra số đơn/số lượng/doanh thu/lợi nhuận/margin, kể cả sản phẩm chưa bán. Không cộng số đơn của các sản phẩm để suy ra tổng số đơn toàn hệ thống.

Các tests đối chiếu doanh thu, AOV, lợi nhuận và gross amount dùng sai số **0,01**; kiểm tra tỷ lệ margin và effective unit price dùng sai số **0,0001**. So sánh NULL được xử lý riêng để thiếu giá trị không bị bỏ qua bởi phép so sánh SQL thông thường.

## Sửa logic Gold

| Model / KPI | Thay đổi |
| --- | --- |
| [`gld_customer_metrics`](../dbt/models/gold/gld_customer_metrics.sql): `avg_order_value` | Tính tổng doanh thu chia số đơn riêng biệt. Trước đó `AVG(line_total)` tính trung bình dòng hàng. |
| `gld_customer_metrics`: `orders_with_discount` | Đếm đơn riêng biệt có ít nhất một dòng giảm giá. Một đơn có hai dòng giảm giá chỉ được đếm một lần. |
| [`gld_sales_summary`](../dbt/models/gold/gld_sales_summary.sql): `online_orders`, `offline_orders` | Đếm `DISTINCT sales_order_id` theo kênh thay cho cộng số dòng hàng. |
| [`gld_product_performance`](../dbt/models/gold/gld_product_performance.sql): `profit_margin_pct` | Bảo vệ mẫu số bằng `NULLIF(total_revenue, 0)` để sản phẩm đã bán nhưng doanh thu bằng 0 không làm hỏng truy vấn. |

Ví dụ kiểm thử: khách hàng có hai đơn trị giá **22** và **10**, trong đó đơn 22 gồm hai dòng giảm giá. AOV đúng là **16**, số đơn giảm giá là **1**; công thức cũ cho khoảng **10,6667** và **2**. Hai dòng online cùng một đơn phải cho `online_orders = 1`.

Quy ước được giữ và kiểm thử:

- Khách chưa có đơn: số đơn và số đơn giảm giá bằng 0; doanh thu, AOV, tổng số lượng và ngày đặt hàng là NULL.
- Sản phẩm chưa bán: số đơn và margin bằng 0; số lượng, doanh thu, giá bán trung bình và lợi nhuận là NULL.
- Sản phẩm đã bán với doanh thu bằng 0: margin là NULL vì tỷ lệ không xác định; lợi nhuận vẫn có thể âm.
- `total_profit` dùng **StandardCost hiện tại**, nên là lợi nhuận ước tính theo chi phí hiện tại, không phải lợi nhuận kế toán theo chi phí lịch sử.
- Doanh thu là tổng giá trị dòng hàng sau giảm giá, không gồm thuế/phí vận chuyển. `avg_order_line_value` vẫn là trung bình dòng hàng; `avg_selling_price` vẫn là trung bình giá đơn vị trước giảm giá theo dòng, không có trọng số số lượng.

## Dữ liệu kiểm thử riêng

[`verify_dbt_test_contracts.py`](../scripts/verify_dbt_test_contracts.py) sao chép **3 macros thật** vào project dbt tạm, tạo hai views trong schema có tên ngẫu nhiên `tuan_test_contracts_*`, chạy các cases hợp lệ/không hợp lệ rồi xóa views và schema. Các cases bao gồm số âm, 0, số dương rất nhỏ, NULL, ngày tương lai, ngày quá khứ, timestamp hiện tại và giá trị hai bên ngưỡng sai số. Tên cột có khoảng trắng kiểm tra việc quote identifier. Script đối chiếu cả trạng thái lẫn số dòng lỗi; `dbt test` trả exit 1 cho bộ dữ liệu cố tình sai là một phần của kỳ vọng.

[`verify_dbt_gold_contracts.py`](../scripts/verify_dbt_gold_contracts.py) render và thực thi **SQL của 3 Gold models hiện có** trên bảng tạm `#customers`, `#products`, `#sales`. Dữ liệu gồm đơn nhiều dòng, đơn miễn phí, khách chưa mua và sản phẩm chưa bán. Runner so với các giá trị kỳ vọng cố định, dùng sai số **0,0001** cho số thập phân. Bảng tạm chỉ tồn tại trong connection và được xóa khi connection đóng. Kết quả ghi hash SQL để truy vết phiên bản đã kiểm thử. Hai scripts không sửa bảng dữ liệu nghiệp vụ.

## Chạy lại trên PowerShell

Điều kiện: chạy tại thư mục gốc repository; services `sqlserver` và `dbt` đang hoạt động; AdventureWorks2014 và login trong profile local đã được thiết lập. Các thư viện của scripts đã có trong image dbt hiện tại. Mỗi lần chạy dùng thư mục mới để giữ nguyên bằng chứng cũ.

```powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$evidence = "docs/evidence/tuan-week1-day3-5/$stamp"
.\scripts\verify_dbt_baseline.ps1 -OutputDirectory "$evidence/baseline"
```

Baseline chạy lần lượt `dbt deps → dbt debug → dbt run → dbt test`; kết quả run và test được lưu riêng. `dbt test` bao gồm schema/source tests, các generic tests đã khai báo và 4 singular tests. Quy trình này kiểm tra sau khi xây dựng models, chưa chặn Silver/Gold ngay khi Bronze có lỗi; khi cần chặn theo dependencies, tích hợp `dbt build` vào CI/DAG.

Sau baseline, chạy hai bộ dữ liệu kiểm thử với cùng `$stamp` và `$evidence`:

```powershell
docker compose cp scripts/verify_dbt_test_contracts.py dbt:/tmp/verify_dbt_test_contracts.py
if ($LASTEXITCODE -ne 0) { throw 'Copy generic fixture runner failed' }
$genericOutput = "/tmp/tuan-generic-$stamp"
docker compose exec -T dbt python /tmp/verify_dbt_test_contracts.py --project-dir /usr/app/dbt --output-dir $genericOutput
if ($LASTEXITCODE -ne 0) { throw 'Generic fixture verification failed; inspect container output' }
docker compose cp "dbt:$genericOutput" "$evidence/generic_contracts"
if ($LASTEXITCODE -ne 0) { throw 'Copy generic fixture evidence failed' }

docker compose cp scripts/verify_dbt_gold_contracts.py dbt:/tmp/verify_dbt_gold_contracts.py
if ($LASTEXITCODE -ne 0) { throw 'Copy Gold fixture runner failed' }
$goldOutput = "/tmp/tuan-gold-$stamp.json"
docker compose exec -T dbt python /tmp/verify_dbt_gold_contracts.py --project-dir /usr/app/dbt --output $goldOutput
if ($LASTEXITCODE -ne 0) { throw 'Gold fixture verification failed; inspect container output' }
docker compose cp "dbt:$goldOutput" "$evidence/gold_contracts.after.json"
if ($LASTEXITCODE -ne 0) { throw 'Copy Gold fixture evidence failed' }
```

Nếu script báo lỗi, artifacts đang có trong đường dẫn `/tmp` đã truyền vào; giữ chúng để điều tra. Chọn timestamp mới cho lần chạy tiếp theo. Các scripts từ chối ghi đè output đã có.

## Bàn giao và phạm vi còn lại

Phần schema/relationships, 3 generic tests và sửa lỗi model ngày 3–5 đã hoàn tất, có bằng chứng kiểm thử trên dữ liệu thật và dữ liệu biên. Kết hợp với baseline/review ngày 1–2, công việc dbt của Tuân trong tuần 1 đã sẵn sàng để review PR và bàn giao tích hợp.

Bảo phụ trách tích hợp các lệnh dbt vào CI có database khả dụng và cấu hình checks bắt buộc; các workflow lint/compile hiện tại chưa chứng minh rằng lỗi `dbt test` sẽ chặn merge. Thịnh phụ trách DAG và kiểm thử Airflow end-to-end. Kết quả tại đây kiểm chứng SQL/dbt và không thay thế checkpoint chung về 5 containers, Airflow hay GitHub Actions.

Source freshness và Great Expectations tiếp tục theo lịch tuần 2–3. AdventureWorks2014 là dữ liệu lịch sử nên cần chọn quy tắc freshness phù hợp, không mặc định yêu cầu dữ liệu năm 2014 phải mới trong vài giờ. Khi tích hợp tuần 2, thống nhất phiên bản dbt giữa môi trường Docker và các cấu hình cài đặt khác, đồng thời giữ quy ước UTC hoặc chuyển đổi timezone trước khi dùng `no_future_dates` với nguồn mới.
