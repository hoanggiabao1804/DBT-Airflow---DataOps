# Báo cáo chất lượng dữ liệu — Tuân, kết thúc tuần 2

**Ngày đánh giá: 16/11/2026. Phần việc tuần 2 của Tuân đã hoàn thành và sẵn sàng review.** Dữ liệu đạt toàn bộ dbt data tests và GE expectations được cấu hình; **cả 6 nguồn không đạt freshness SLA demo**. Trạng thái chất lượng tổng hợp là `failed_freshness`, không phải PASS toàn bộ.

Báo cáo hoàn tất nhiệm vụ ngày 10 trong `Project-Devops.md`: kiểm tra kết quả validation và báo cáo chất lượng dữ liệu. Đây là nghiệm thu phần Tuân; không xác nhận các nhiệm vụ deployment, alert hoặc pipeline tích hợp của cả nhóm đã hoàn thành.

## 1. Phạm vi và bằng chứng

- Code được kiểm tra: `ae97a1c684c2098cd1a8bd68f3fa7b58c914b15c` trên `develop`, sau PR #11. Nhánh báo cáo: `feature/tuan-week2-day10`.
- Môi trường: SQL Server/AdventureWorks2014, dbt target `dev`, GE đọc schema `silver`.
- Cửa sổ chạy chốt: **17:03:24–17:06:35 giờ Việt Nam**, ngày 16/11/2026, tương ứng **10:03:24–10:06:35 UTC**. Các lệnh chạy tuần tự trên môi trường lab; đây không phải một transaction snapshot chung của database.
- dbt 1.8.7/sqlserver 1.8.7; GE 0.18.22 trong container riêng. Ngày 10 dùng các runners đã kiểm chứng, không thay đổi models, rules hoặc ngưỡng freshness.
- [Tổng hợp có cấu trúc và SHA-256](evidence/tuan-week2-day10/20261116/quality_summary.json), [chỉ mục bằng chứng](evidence/tuan-week2-day10/20261116/README.md).

## 2. Kết quả lần chạy chốt

| Thành phần | Phạm vi | Kết quả | Exit code | Bằng chứng |
| --- | --- | --- | ---: | --- |
| dbt baseline | deps → debug → run → test | 10/10 models thành công; 200/200 tests PASS, 0 WARN/FAIL/ERROR/SKIP | 0 | [baseline status](evidence/tuan-week2-day10/20261116/baseline/baseline_status.json), [test results](evidence/tuan-week2-day10/20261116/baseline/test.run_results.json) |
| Timestamp nguồn | 6 bảng, mỗi bảng not-null và no-future | 12/12 PASS | 0 | [timestamp results](evidence/tuan-week2-day10/20261116/freshness/timestamp_tests.run_results.json) |
| Source freshness | 6 bảng đang dùng, warn 24h/error 48h | 6 ERROR STALE, 0 PASS/WARN; truy vấn thực thi bình thường | 1 | [freshness status](evidence/tuan-week2-day10/20261116/freshness/freshness_status.json), [sources.json](evidence/tuan-week2-day10/20261116/freshness/sources.json) |
| GE customer | Toàn bộ 19.820 dòng khách hàng | 10/10 expectations PASS | 0 | [customer checkpoint](evidence/tuan-week2-day10/20261116/ge/customer_checkpoint.json) |
| GE order | Toàn bộ 121.317 dòng đơn hàng | 30/30 expectations PASS | 0 | [order checkpoint](evidence/tuan-week2-day10/20261116/ge/order_checkpoint.json) |

12 timestamp tests là **tập con của 200 dbt tests**, không cộng thành 212. Hai checkpoint GE có tổng 40 expectations; một số kiểm tra trùng mục đích với dbt, nên không gọi đây là 240 quy tắc độc lập. Số 121.317 là **dòng đơn hàng**, không phải số đơn hàng phân biệt. Tỷ lệ tests PASS không phải điểm chất lượng tổng thể của dữ liệu.

CI trên chính commit `ae97a1c` đã thành công: [DBT CI Pipeline](https://github.com/hoanggiabao1804/DBT-Airflow---DataOps/actions/runs/43844582344), [Python Code Quality](https://github.com/hoanggiabao1804/DBT-Airflow---DataOps/actions/runs/43844582278). Workflow hiện có chạy dbt; **GE và source freshness chưa phải gate tự động trong CI**. GE trong báo cáo này được chạy thật tại môi trường Docker local.

## 3. Phạm vi chất lượng được kiểm tra

| Nhóm dbt tests | Số test nodes | Mục đích |
| --- | ---: | --- |
| `not_null` | 92 | Các cột bắt buộc |
| `unique` | 15 | Khóa/cột duy nhất |
| `relationships` | 15 | Quan hệ khóa nguồn/model |
| `accepted_values` | 13 | Miền giá trị |
| `positive_values` | 33 | Giá trị dương/không âm theo từng trường |
| `no_future_dates` | 21 | Timestamp không tương lai |
| `line_total_matches` | 2 | Công thức doanh thu dòng hàng |
| Composite unique | 3 | Khóa ghép dòng đơn hàng |
| Accepted range | 2 | Khoảng giá trị |
| Singular reconciliation | 4 | Dòng hàng Bronze→Silver và customer/product/daily metrics ở Gold |
| **Tổng** | **200** | **Cùng chính xác 200 test IDs đã nghiệm thu ngày 6–7** |

GE customer kiểm tra đủ 8 cột, bảng không rỗng, khóa, các trường tên không NULL, miền email preference và timestamp. GE order kiểm tra đủ 20 cột, bảng không rỗng, khóa ghép, 16 cột bắt buộc, quantity, giá/doanh thu, discount, status/channel/flag và timestamp. Các phép tính doanh thu, đối chiếu tầng và khóa ngoại đã có tests dbt riêng.

Giới hạn cần giữ khi diễn giải kết quả:

- Tests chứng minh các quy tắc đã khai báo, không xác minh mọi khía cạnh nghiệp vụ hay độ chính xác so với hệ thống nguồn bên ngoài.
- GE chỉ kiểm tra customer/order ở Silver; dữ liệu không hợp lệ bị model lọc phải được phát hiện tại Bronze bằng dbt tests. Số lượng và giá trị hợp lệ đi từ Bronze sang Silver đã có singular test riêng.
- Freshness chỉ áp dụng 6 nguồn đang dùng. Bảy khai báo nguồn `raw` chưa được models sử dụng không nằm trong kết quả freshness.
- Tên `Unknown` hợp lệ theo model. GE kiểm tra tên không NULL, không chứng minh trim/format hay danh tính khách hàng chính xác.
- **701 khách hàng có `email_promotion` NULL**, được phép theo quy tắc khách cửa hàng; kết quả không ghi nhận đây là lỗi. [Metric missing_count](evidence/tuan-week2-day10/20261116/ge/customer_checkpoint.json).
- Giá bằng 0, discount 100%, ship date NULL và due date tương lai là hợp lệ. Các KPI Gold của khách/sản phẩm chưa giao dịch có thể NULL; lợi nhuận âm không tự động là lỗi.

## 4. Phát hiện còn mở: nguồn không đạt độ mới

**DQ-W2-01 — OPEN, không đạt SLA demo 24h/48h.** Timestamp mới nhất của cả sáu bảng đều quá hạn:

| Nguồn | MAX(ModifiedDate), UTC | Tuổi dữ liệu tại lần kiểm tra, ngày | Trạng thái |
| --- | --- | ---: | --- |
| Sales.Customer | 2014-09-12 11:15:07.263 | 4.448,0 | ERROR STALE |
| Sales.SalesOrderHeader | 2014-07-07 00:00:00 | 4.515,4 | ERROR STALE |
| Sales.SalesOrderDetail | 2014-06-30 00:00:00 | 4.522,4 | ERROR STALE |
| Person.Person | 2015-04-15 16:33:33.123 | 4.232,7 | ERROR STALE |
| Production.Product | 2014-02-08 10:03:55.510 | 4.664,0 | ERROR STALE |
| Production.ProductSubcategory | 2008-04-30 00:00:00 | 6.774,4 | ERROR STALE |

Đây là dữ liệu AdventureWorks lịch sử; `ModifiedDate` là thời điểm cập nhật nghiệp vụ, không phải thời điểm ingest/restore. Việc restore hôm nay hoặc chạy dbt thành công không làm các timestamp này mới hơn. Tuổi dữ liệu làm tròn một chữ số thập phân; giá trị gốc có trong `sources.json`.

**Ảnh hưởng:** dataset vẫn dùng để demo transformations và kiểm tra quy tắc; chưa chứng minh khả năng cấp dữ liệu cập nhật hằng ngày. GE PASS và CI xanh không đóng được phát hiện này.

**Xử lý/bàn giao:** Tuân chịu trách nhiệm diễn giải watermark và đề xuất SLA với nhóm; khi có luồng nạp dữ liệu thật, cần timestamp ingestion/heartbeat đáng tin cậy và SLA phù hợp từng nguồn, đặc biệt danh mục ít thay đổi. Sau đó phối hợp Bảo/Thịnh đưa freshness vào gate, chạy lại và giữ nguyên exit code. Chỉ đóng DQ-W2-01 khi có bằng chứng đạt chính sách đã thống nhất. Không sửa timestamp, dịch đồng hồ hoặc tăng ngưỡng lên nhiều năm để làm xanh dataset mẫu.

## 5. Khả năng phát hiện lỗi đã được chứng minh

Các kiểm thử tình huống trước đó được đối chiếu SHA-256 với cấu hình hiện tại và giữ nguyên hiệu lực; **không chạy lại fixtures trong ngày 10** vì các rules liên quan không thay đổi:

- [Freshness/timestamp fixtures ngày 6–7](evidence/tuan-week2-day6-7/20261116/contracts/summary.json): **17/17 assertions** khớp kỳ vọng trên 7 tình huống fresh/warn/stale/NULL/future/mixed-null/empty; đã xác minh cleanup.
- [GE fixtures ngày 8–9](evidence/tuan-week2-day8-9/20261116/contracts/summary.json): **8/8 scenarios** khớp kỳ vọng, gồm dữ liệu hợp lệ, trùng khóa, NULL bắt buộc, sai miền/range, timestamp tương lai, bảng rỗng và lỗi thiếu bảng. CLI đã xác nhận PASS exit 0, vi phạm dữ liệu exit 1, lỗi thực thi exit 2; đã xác minh cleanup.

Những FAIL cố ý trong fixtures chứng minh khả năng phát hiện lỗi, không phải lỗi của dữ liệu Silver thật. Kết quả thật ngày 10 nằm riêng tại `tuan-week2-day10/20261116/`.

## 6. Nghiệm thu phần Tuân tuần 2

| Nhiệm vụ được giao | Trạng thái | Bằng chứng |
| --- | --- | --- |
| Ngày 6–7: hoàn tất schema/custom tests và source freshness | Hoàn thành triển khai/kiểm thử; DQ-W2-01 vẫn mở đối với dữ liệu mẫu | [Báo cáo ngày 6–7](tuan_week2_day6_7.md), [PR #10 đã merge](https://github.com/hoanggiabao1804/DBT-Airflow---DataOps/pull/10) |
| Ngày 8–9: cấu hình GE, customer/order suites và checkpoints | Hoàn thành; 2 suites và 2 checkpoints chạy được | [Báo cáo ngày 8–9](tuan_week2_day8_9.md), [PR #11 đã merge](https://github.com/hoanggiabao1804/DBT-Airflow---DataOps/pull/11) |
| Ngày 10: kiểm tra validation, báo cáo chất lượng | Hoàn thành báo cáo và lần chạy chốt; sẵn sàng review | Báo cáo này, [quality_summary.json](evidence/tuan-week2-day10/20261116/quality_summary.json) |

Tuân không còn nhiệm vụ triển khai/báo cáo tuần 2 chưa làm trong phạm vi trên. DQ-W2-01 được giữ công khai là giới hạn/phát hiện dữ liệu, không được xóa chỉ vì phần code đã hoàn thành. Nghiệm thu alert, deployment hoặc Airflow end-to-end của cả nhóm nằm ngoài kết luận này.

## 7. Bàn giao sang tuần 3

1. **Ngày 11–12:** Tuân phối hợp Thịnh tích hợp GE với Airflow, giữ exit code và artifacts; hoàn thiện tests/dbt docs. Chưa có bằng chứng GE chạy tự động trong DAG ở lần nghiệm thu này.
2. **Ngày 13:** kiểm tra số liệu Bronze → Silver → Gold và test coverage trong pipeline tích hợp.
3. **Ngày 14:** hoàn thiện lineage và tài liệu tests.
4. **Ngày 15:** demo models, dbt tests và GE; trình bày rõ DQ-W2-01 khi dùng dữ liệu mẫu.

CI/deployment do Bảo phụ trách; DAG/alert/monitoring phối hợp Thịnh. Báo cáo không nhận thay các phần việc đó.

## 8. Chạy lại để cập nhật báo cáo

Chạy từ gốc repository, Docker/SQL Server/dbt đang hoạt động, database đã restore và profile local hợp lệ. Không chạy hai `dbt deps` đồng thời.

```powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$evidence = "docs/evidence/tuan-week2-day10/$stamp"
.\scripts\verify_dbt_baseline.ps1 -OutputDirectory "$evidence/baseline"
.\scripts\verify_dbt_freshness.ps1 -OutputDirectory "$evidence/freshness" -Target dev
$freshnessExit = $LASTEXITCODE
Write-Host "Freshness exit: $freshnessExit"

docker compose -f docker-compose.yml -f docker-compose.ge.yml --profile quality run --rm --no-deps ge --target dev --schema silver --output-dir "/evidence/week2-day10-$stamp"
$geExit = $LASTEXITCODE
Write-Host "GE exit: $geExit"
```

Freshness exit 1 phải được ghi nhận là không đạt SLA; exit 2 là lỗi thực thi và không được coi là stale dự kiến. GE output ở `great_expectations/uncommitted/week2-day10-<stamp>/`; lưu cùng kết quả dbt rồi cập nhật báo cáo theo nội dung JSON thực tế, không chỉ đọc chữ PASS trong console. Cách build image và chạy fixture: [GE README](../great_expectations/README.md), [hướng dẫn freshness](tuan_week2_day6_7.md).
