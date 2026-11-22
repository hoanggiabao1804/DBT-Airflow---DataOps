# Tuân — ngày 15: demo dbt models, tests và Great Expectations

Phạm vi ngày 15 theo phân công là trình bày **dbt models, tests và GE**. Runbook này dành cho phần nói khoảng **12 phút** của Tuân. Bằng chứng chạy thử ngày **19/11/2026** được lưu ở [hồ sơ ngày 15](evidence/tuan-week3-day15/20261119/README.md). Chạy thử trên máy và trình bày trước người nghe là hai việc khác nhau; hồ sơ kỹ thuật không xác nhận đã có buổi demo với nhóm/giảng viên.

**Đã chạy thử kỹ thuật thành công ngày 19/11/2026, từ 20:00:59 đến 20:11:37 giờ Việt Nam**, run `tuan-day15-20261119-01`, code `2971267df716f220f78ab047f9a91c0428effa66`. Kết quả: 10 models, 202 dbt tests, 40 GE expectations PASS; 20 kiểm tra đối chiếu đạt. Các bộ fixtures đạt 8 assertions generic, 27 assertions đối chiếu và 8 tình huống GE; cả ba xác nhận cleanup. [acceptance.json](evidence/tuan-week3-day15/20261119/acceptance.json) ghi phạm vi và giới hạn; việc Tuân trình bày trước nhóm/giảng viên vẫn cần thực hiện.

## Chuẩn bị trước khi đến lượt trình bày

Mở repository ở đúng commit đã chạy thử. Chuẩn bị ba cửa sổ: trình duyệt xem dbt docs, trình soạn thảo xem SQL/JSON và PowerShell ở thư mục gốc project. Mở sẵn [data lineage](tuan_data_lineage.md), [test catalog](tuan_test_catalog.md) và [evidence ngày 15](evidence/tuan-week3-day15/20261119/README.md); không đọc hết chúng trong 12 phút.

SQL Server phải đã restore AdventureWorks2014, profile local kết nối được và Docker đang chạy. Lượt ngày 15 dùng ba services `sqlserver`, `dbt`, `ge-worker`, thực thi tuần tự bằng lệnh thủ công. Hoàn thành lượt chạy thật và fixtures trước buổi demo; thời gian dựng image, khởi động services và chạy toàn bộ tests không tính vào phần nói. Không chạy fixture/dbt thủ công đồng thời với DAG đang build dữ liệu.

Docs của lượt chạy thử đã có tại `dbt/target/tuan-day15-20261119-01/docs/` trên máy đã chạy; manifest/catalog có đủ 10 models và 131 cột được mô tả. Mở server local trong một cửa sổ riêng để trình bày đúng artifacts đó:

```powershell
python -m http.server 8081 --bind 127.0.0.1 --directory dbt/target/tuan-day15-20261119-01/docs
```

Mở `http://127.0.0.1:8081`, tìm `gld_customer_metrics`, rồi mở lineage và Columns/Tests. Giữ server chạy trong khi trình bày; kết thúc bằng `Ctrl+C`. Thư mục target bị Git ignore: máy mới cần tạo docs bằng phần lệnh chạy lại bên dưới và phục vụ đường dẫn mới. `docs generate` chỉ tạo tài liệu/metadata, không chạy lại models, tests hoặc GE. Nếu dùng docs từ task Airflow, phục vụ đúng thư mục attempt `dbt_docs` được ghi trong evidence.

## Sáu màn hình / ý chính để nói

| Thời gian | Màn hình mở | Thao tác và lời giải thích |
| --- | --- | --- |
| 0:00–1:00 | Lineage | “Phần của Tuân là chuyển đổi và kiểm tra chất lượng dữ liệu: 6 nguồn đang dùng → 4 Bronze views → 3 Silver tables → 3 Gold tables. Có 15 dependency edges.” Chỉ nhánh sales và hai dimensions customer/product. |
| 1:00–3:00 | SQL Silver sales và Gold customer/daily | Chỉ grain dòng hàng, bộ lọc hợp lệ và hai công thức trung bình ở mục dưới. Phân biệt số dòng với số đơn hàng; không gọi `SUM(product.total_orders)` là tổng đơn hàng toàn hệ thống. |
| 3:00–5:00 | dbt docs và kết quả dbt ngày 15 | Mở Columns/Tests của một model, rồi kết quả đủ 10 models và 202 tests. Chọn ba generic tests tự viết và một singular test để giải thích vì sao PASS có ý nghĩa. |
| 5:00–7:00 | Kết quả GE ngày 15 | Chỉ `customer_checkpoint` 10 rules và `order_checkpoint` 30 rules, trạng thái tổng và số dòng đã kiểm tra. Giải thích GE áp dụng hai bảng Silver; các quan hệ khóa ngoại/công thức/đối chiếu Gold tiếp tục do dbt kiểm tra. |
| 7:00–10:00 | Kết quả fixtures dbt và GE | Mở ca hợp lệ, ca cố ý sai và ca thiếu bảng. Chỉ expected/actual exit, rule hoặc số vi phạm, rồi `cleanup_verified`. Giải thích verifier PASS vì đã bắt đúng lỗi dự kiến. |
| 10:00–12:00 | Freshness và evidence index | Nêu `DQ-W2-01` còn mở, chỉ timestamp/run ID/commit của bằng chứng và trả lời câu hỏi. Chuyển phần demo Airflow/monitoring/incident cho Thịnh, PR/CI/CD cho Bảo. |

Đây cũng là dàn ý sáu slide nếu nhóm dùng slide chung. Nội dung cần chứng minh nằm trong SQL, docs và artifacts được mở trực tiếp; không cần chép toàn bộ JSON vào slide.

## Đoạn giải thích models trong hai phút

Mở [slvr_sales_orders.sql](../dbt/models/silver/slvr_sales_orders.sql). Một dòng là **một chi tiết đơn hàng**, khóa `(sales_order_id, order_detail_id)`; một `sales_order_id` xuất hiện nhiều lần là bình thường. Silver giữ `order_qty > 0 AND unit_price >= 0`; NULL không thỏa điều kiện cũng bị loại. Doanh thu dùng `line_total` sau discount, chưa bao gồm thuế/phí vận chuyển.

Mở [gld_customer_metrics.sql](../dbt/models/gold/gld_customer_metrics.sql) và [gld_sales_summary.sql](../dbt/models/gold/gld_sales_summary.sql):

- Customer `avg_order_value = SUM(line_total) / COUNT(DISTINCT sales_order_id)`: giá trị trung bình **một đơn** của khách hàng.
- Daily `avg_order_line_value = AVG(line_total)`: giá trị trung bình **một dòng hàng** trong ngày.
- Ví dụ minh họa: cùng một khách có một đơn hai dòng 20 và 30, đơn khác một dòng 10 trong cùng ngày. AOV là `60 / 2 = 30`, còn trung bình dòng là `60 / 3 = 20`. Đây là ví dụ tính tay, không phải số đo AdventureWorks.
- Gold customer/product LEFT JOIN sales giữ cả đối tượng chưa có giao dịch. `total_orders` bằng 0 nhưng một số SUM/AVG vẫn NULL; không đổi toàn bộ NULL thành 0 để làm tests xanh.

Nếu được hỏi thêm, product `avg_selling_price` là trung bình đơn giá trước discount theo dòng, không gia quyền số lượng. Profit dùng `standard_cost` hiện tại, không phải giá vốn lịch sử. [Lineage ngày 14](tuan_data_lineage.md) ghi rõ các giới hạn này.

## Cách đọc bằng chứng PASS

Mở [evidence ngày 15](evidence/tuan-week3-day15/20261119/README.md) và đi theo các đường dẫn của đúng lượt chạy. Trước khi nói kết quả, đọc ngày giờ, run ID và commit; không lấy artifacts ngày 13 để gọi là vừa chạy hôm nay.

| Bằng chứng | Trường cần chỉ cho người nghe | Tiêu chí |
| --- | --- | --- |
| [dbt run](evidence/tuan-week3-day15/20261119/production/dbt_run.run_results.json) | `metadata.invocation_id`, `results[].unique_id`, `results[].status` | Đủ 10 model results, tất cả `success`. |
| [dbt test](evidence/tuan-week3-day15/20261119/production/dbt_test.run_results.json) | Cùng invocation với manifest của bước test; từng ID/status | Đủ 202 test IDs, tất cả `pass`, không skip/error/fail; 196 generic + 6 singular. |
| [Coverage](evidence/tuan-week3-day15/20261119/test_coverage.json) | Số test nodes, tập ID, missing/extra/non-PASS | Artifact được đối chiếu đúng invocation; không chỉ đếm các dòng chữ PASS trong log. |
| [GE summary](evidence/tuan-week3-day15/20261119/production/ge/summary.json) | `status`, `exit_code`, `validations` và từng rule ID | Hai checkpoints, đủ 10 + 30 rules, đều đạt; exit 0. |
| [Reconciliation](evidence/tuan-week3-day15/20261119/layer_reconciliation.json) | Trạng thái kiểm tra và số vi phạm | Dùng thêm để giải thích số lượng/doanh thu Bronze → Silver → Gold; không cộng vào số 202 dbt nodes. |

Ba custom tests tiêu biểu: `positive_values` kiểm tra dấu và có tùy chọn cho phép 0; `no_future_dates` dùng đồng hồ UTC; `line_total_matches` kiểm tra `qty × price × (1 − discount)` trong ngưỡng tuyệt đối 0,01. Cả ba bỏ qua NULL, vì vậy `not_null` là quy tắc riêng. Chọn `assert_daily_sales_reconciliation` để minh họa kiểm tra số liệu theo từng ngày; hai ngày sai bù trừ không thể che nhau chỉ vì tổng doanh thu toàn bảng bằng nhau.

Không gọi 202 dbt tests + 40 GE expectations là 242 quy tắc nghiệp vụ độc lập: có kiểm tra trùng mục đích. Tỷ lệ PASS không phải tỷ lệ bao phủ nghiệp vụ; 86/131 cột có generic tests trực tiếp cũng không phải “65,6% dữ liệu đúng”.

## Demo dữ liệu sai và mã thoát

Chạy các verifier hiện có trước buổi nói. Chúng chỉ tạo dữ liệu tổng hợp trong schema UUID hoặc bảng tạm của connection. Không sửa dữ liệu Silver thật để tạo lỗi trình diễn. Mở [generic fixtures](evidence/tuan-week3-day15/20261119/generic_contracts/summary.json), [reconciliation fixtures](evidence/tuan-week3-day15/20261119/reconciliation_contracts.json) và [GE fixtures](evidence/tuan-week3-day15/20261119/ge_contracts/summary.json), rồi chỉ rõ tình huống:

| Tình huống | Kết quả cần thấy | Cách nói |
| --- | --- | --- |
| dbt generic: bộ dữ liệu hợp lệ và sai trong cùng fixture project | 4 tests PASS, 4 tests FAIL có số vi phạm đúng; native `dbt test` exit 1 | “Giá trị âm, timestamp tương lai và công thức lệch ngưỡng đã bị bắt. Lỗi này được tạo có chủ đích.” |
| dbt reconciliation: sai KPI, mất/thừa/thay khóa hoặc hai ngày sai bù trừ | Số vi phạm thực tế bằng số kỳ vọng; baseline và sau rollback đều 0 | “Đối chiếu theo nhóm và tập khóa phát hiện lỗi mà chỉ so tổng/số dòng có thể bỏ sót.” |
| GE `valid_nullable_free_discount_multiline` | Checkpoints PASS, native CLI exit 0 | “NULL tùy chọn, giá 0, discount 100% và đơn nhiều dòng là hợp lệ.” |
| GE `empty_tables` | Hai rule `customer_nonempty`/`order_nonempty` FAIL, native CLI exit 1 | “Kết nối thành công nhưng dữ liệu không đạt, cần xử lý chất lượng dữ liệu.” |
| GE `missing_table_runtime_error` | Trạng thái `error`, native CLI exit 2 | “Không thể kiểm tra do thiếu bảng; đây là lỗi thực thi, khác dữ liệu không đạt.” |

GE `invalid_domains` còn minh họa `email_promotion=3`, `status=7`, channel sai và `has_discount=2`; các rule tương ứng phải FAIL. Ca này gọi runner Python trực tiếp, nên báo cáo ghi native CLI là false. Dùng `empty_tables` khi cần chứng minh mã thoát thật của tiến trình CLI là 1.

**Mã thoát verifier khác mã thoát validation bên trong.** Verifier trả 0 khi mọi ca đều đúng kỳ vọng và đã dọn fixture, kể cả các ca cố ý có native exit 1/2. Nó trả khác 0 nếu không bắt đúng lỗi, không đọc được bằng chứng hoặc cleanup thất bại. Khi kết thúc, chỉ `cleanup_verified: true` trong báo cáo; không chỉ dựa vào dòng chữ cuối terminal.

## Lệnh chạy lại khi tập dượt

Các lệnh dưới đây chạy tại gốc repository khi stack đã sẵn sàng. Mỗi lượt dùng đường dẫn mới để giữ bằng chứng cũ. Kiểm tra `$LASTEXITCODE` ngay sau từng lệnh; không tiếp tục nếu một bước ngoài dự kiến thất bại.

Lượt ngày 15 dùng các bước dbt → GE → docs thủ công, có mã thoát kiểm tra ngay sau mỗi bước. Nó chứng minh kết quả của models/tests/GE trên môi trường local; không phải một lượt scheduler DAG mới. Bằng chứng tích hợp scheduler trước đó nằm ở [ngày 13](tuan_week3_day13.md). Khởi động ba services cần thiết, rồi chạy:

```powershell
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml up -d sqlserver dbt ge-worker
if ($LASTEXITCODE -ne 0) { throw 'Demo services could not start' }
$demoStamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$demoTarget = "target/tuan-day15-$demoStamp"
docker compose exec -T dbt dbt deps --profiles-dir . --target dev
if ($LASTEXITCODE -ne 0) { throw 'dbt deps failed' }
docker compose exec -T dbt dbt run --profiles-dir . --target dev --target-path "$demoTarget/run"
if ($LASTEXITCODE -ne 0) { throw 'dbt run failed' }
docker compose exec -T dbt dbt test --profiles-dir . --target dev --target-path "$demoTarget/test"
if ($LASTEXITCODE -ne 0) { throw 'dbt test failed' }
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T ge-worker python /workspace/scripts/run_ge_checkpoints.py --target dev --schema silver --output-dir "/evidence/day15-$demoStamp/production/ge"
if ($LASTEXITCODE -ne 0) { throw 'GE production validation failed' }
docker compose exec -T dbt dbt docs generate --profiles-dir . --target dev --target-path "$demoTarget/docs"
if ($LASTEXITCODE -ne 0) { throw 'dbt docs generate failed' }
```

dbt artifacts ở `dbt/$demoTarget/{run,test,docs}/`; GE ở `great_expectations/uncommitted/day15-$demoStamp/production/ge/`. Đọc kết quả của đúng đường dẫn vừa chạy, không lấy manifest từ `docs` ghép với `run_results.json` của `test`. Chỉ tạo target mới chưa tồn tại để tránh nhầm bằng chứng giữa các lượt. Nếu muốn phục vụ docs vừa tạo, đổi đường dẫn server local thành `"dbt/$demoTarget/docs"`.

Tạo báo cáo coverage trên máy host bằng Python 3; script chỉ dùng thư viện chuẩn. Baseline ngày 13 dùng để so sánh tập ID, còn trạng thái PASS của lượt mới phải đến từ manifest và `run_results.json` vừa tạo:

```powershell
python scripts/report_dbt_test_coverage.py --manifest "dbt/$demoTarget/test/manifest.json" --run-results "dbt/$demoTarget/test/run_results.json" --baseline-results docs/evidence/tuan-week3-day13/20261117/production/dbt_test.run_results.json --output "great_expectations/uncommitted/day15-$demoStamp/test_coverage.json"
if ($LASTEXITCODE -ne 0) { throw 'dbt coverage verification failed' }

docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T ge-worker python /workspace/scripts/reconcile_dbt_layers.py --project-dir /workspace/dbt --target dev --manifest "/workspace/dbt/$demoTarget/test/manifest.json" --run-results "/workspace/dbt/$demoTarget/test/run_results.json" --output-dir "/evidence/day15-$demoStamp/layer_reconciliation"
if ($LASTEXITCODE -ne 0) { throw 'Layer reconciliation failed' }
```

Báo cáo đối chiếu nằm ở `great_expectations/uncommitted/day15-$demoStamp/layer_reconciliation/summary.json`; khi chọn bằng chứng bàn giao có thể sao chép thành `layer_reconciliation.json`. Các truy vấn chỉ đọc chạy trong một transaction `SERIALIZABLE` sau dbt; đây không phải snapshot dùng chung với bước build trước đó. Giữ dữ liệu ổn định trong lúc thu bằng chứng.

Sau khi các bước dữ liệu thật kết thúc, chạy fixtures GE và reconciliation lần lượt:

```powershell
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T ge-worker python /workspace/scripts/verify_ge_contracts.py --target dev --output-dir "/evidence/day15-ge-contracts-$demoStamp"
if ($LASTEXITCODE -ne 0) { throw 'GE fixture verification failed' }

docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T ge-worker python /workspace/scripts/verify_dbt_reconciliation_contracts.py --project-dir /workspace/dbt --output "/evidence/day15-reconciliation-contracts-$demoStamp.json"
if ($LASTEXITCODE -ne 0) { throw 'dbt reconciliation fixture verification failed' }
```

Riêng `verify_dbt_reconciliation_contracts.py` dùng target mặc định trong `dbt/profiles.yml`, không có tham số `--target`. Trước khi chạy, bảo đảm target mặc định là `dev` và trỏ đúng SQL Server local đã dùng ở trên; không in profile hoặc connection string ra màn hình demo.

Generic verifier cần môi trường dbt, và service `dbt` không mount thư mục `scripts`, nên chép runner vào `/tmp` trước. Bằng chứng đặt trong target đã bị Git ignore:

```powershell
docker compose cp scripts/verify_dbt_test_contracts.py dbt:/tmp/verify_dbt_test_contracts.py
if ($LASTEXITCODE -ne 0) { throw 'Could not copy generic verifier' }
docker compose exec -T dbt python /tmp/verify_dbt_test_contracts.py --project-dir /usr/app/dbt --profiles-dir /usr/app/dbt --target dev --output-dir "/usr/app/dbt/target/day15-generic-contracts-$demoStamp"
if ($LASTEXITCODE -ne 0) { throw 'dbt generic fixture verification failed' }
```

GE/reconciliation output ở `great_expectations/uncommitted/`, generic output ở `dbt/target/`. Chọn các báo cáo an toàn, tổng hợp của đúng lượt để bàn giao; không commit profile, connection string, toàn bộ log hoặc dữ liệu customer.

Nếu muốn kiểm tra freshness riêng, gọi script hiện có trong tiến trình PowerShell con vì script trả mã thoát:

```powershell
powershell -NoProfile -File scripts/verify_dbt_freshness.ps1 -Target dev -OutputDirectory "great_expectations/uncommitted/day15-freshness-$demoStamp"
$freshnessExit = $LASTEXITCODE
Write-Host "Freshness exit: $freshnessExit"
```

Exit 1 trên snapshot lịch sử là kết quả stale cần đọc trong `freshness_status.json`/`sources.json`, không phải lý do bỏ qua kết quả. Exit 2 là lỗi thực thi hoặc xác minh bằng chứng. Giữ nguyên SLA 24/48 giờ và timestamps nguồn.

## Câu hỏi thường gặp và kết thúc phần của Tuân

| Câu hỏi | Câu trả lời ngắn |
| --- | --- |
| Tất cả tests xanh thì dữ liệu mới chưa? | Chưa. `no_future_dates` chỉ loại timestamp tương lai; freshness đo độ cũ. Sáu nguồn AdventureWorks lịch sử còn `DQ-W2-01` OPEN. ModifiedDate là business watermark, không phải thời điểm restore. |
| GE thay thế dbt tests được không? | Phạm vi hiện tại bổ sung nhau: GE customer/order Silver; dbt còn kiểm tra sources, relationships, công thức và Gold reconciliation. |
| Vì sao không đếm rows để xác nhận mọi thứ? | Một khóa mất và khóa khác thêm có thể giữ nguyên số dòng; hai nhóm sai bù trừ giữ nguyên tổng. Cần đối chiếu tập khóa và KPI từng nhóm. |
| Đã kiểm tra mọi cột chưa? | Có mô tả 131 cột, nhưng mô tả không phải kiểm thử. Generic tests trực tiếp, singular và GE có phạm vi riêng; chi tiết/giới hạn được công khai trong test catalog. |
| Bằng chứng này nghiệm thu toàn bộ dự án chưa? | Chỉ xác nhận phần Tuân và đúng những lượt chạy được lưu. CI/CD, deployment, alert, incident và demo trước người nghe có bàn giao riêng. |

Khi trình bày thực tế, Tuân tự mở các màn hình theo bảng thời gian, nói rõ ngày của evidence và trả lời câu hỏi. Ghi nhận buổi trình bày sau khi nó xảy ra; không đánh dấu đã demo với nhóm chỉ vì rehearsal PASS. Nếu Docker gặp sự cố lúc trình bày, mở evidence đã chạy và công bố đây là bản ghi của ngày/giờ trong hồ sơ, thay vì mô tả là đang chạy trực tiếp.
