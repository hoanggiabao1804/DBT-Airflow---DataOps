# Tuân — Tuần 2, ngày 6–7: tests và source freshness

Ngày thực hiện: **16/11/2026**, Asia/Saigon (UTC+7). Nhánh `feature/tuan-week2-day6-7`, tách từ `develop` tại `4ba31ec`, sau các PR CI/deployment của nhóm.

Phạm vi theo `Project-Devops.md`: hoàn tất schema/custom tests và cấu hình source freshness. Great Expectations thuộc ngày 8–9, chưa nằm trong thay đổi này.

## Kết quả

- `dbt debug` thành công; **10/10 models** chạy thành công.
- **200/200 data tests PASS**: giữ 188 tests tuần 1 và thêm 12 tests timestamp nguồn.
- Freshness trên dữ liệu AdventureWorks2014: **6/6 nguồn ERROR STALE**, không phải lỗi truy vấn. Timestamp mới nhất thực tế nằm trong khoảng **2008–2015**. Kết quả này không đạt SLA dữ liệu cập nhật hằng ngày.
- Bộ fixture riêng: **17/17 assertions khớp kỳ vọng**, gồm 3 lần kiểm tra freshness và 14 timestamp tests trên 7 tình huống. Đã xác minh dọn schema bằng connection mới.
- Python runner đã kiểm tra Black/Flake8; PowerShell runner kiểm tra syntax và từ chối ngưỡng không hợp lệ.

[Bằng chứng và các lần chạy](evidence/tuan-week2-day6-7/20261116/README.md). Các kết quả PASS của data tests không thay thế kết quả freshness.

## Rà soát và bổ sung tests

Các tests tuần 1 đã bao phủ khóa, khóa ghép dòng hàng, quan hệ nguồn/model, miền giá trị, giá/số lượng, công thức dòng hàng và đối chiếu Bronze → Silver → Gold. Giữ nguyên các quy ước cho NULL, giao dịch miễn phí, khách/sản phẩm chưa giao dịch; không thêm tests trùng chỉ để tăng số lượng.

Khoảng trống cần bổ sung cho freshness là `ModifiedDate` trên 6 bảng nguồn đang dùng:

| Schema | Bảng | Tests mới |
| --- | --- | --- |
| Sales | Customer, SalesOrderHeader, SalesOrderDetail | `not_null` và `no_future_dates` trên từng `ModifiedDate` |
| Production | Product, ProductSubcategory | Như trên |
| Person | Person | Như trên |

12 tests mang tag `source_timestamp`, có thể chạy riêng bằng `dbt test --select tag:source_timestamp`. Bảy khai báo nguồn `raw` chưa được models dùng không được đưa vào freshness.

## Chính sách freshness và giới hạn dữ liệu mẫu

[Source YAML](../dbt/models/bronze/src_adventureworks.yml) dùng cú pháp tương thích **dbt Core/sqlserver 1.8.7**:

- `loaded_at_field: "[ModifiedDate]"`.
- Cảnh báo sau **24 giờ**, lỗi sau **48 giờ**. Đây là ngưỡng demo cho nguồn cập nhật hằng ngày, cần thống nhất SLA thực tế trước khi áp dụng production, đặc biệt với danh mục ít thay đổi.
- Có thể cấu hình `source_freshness_warn_hours` và `source_freshness_error_hours` qua `--vars`; phải thỏa `0 < warn < error`.
- [Macro SQL Server](../dbt/macros/sqlserver__collect_freshness.sql) lấy `SYSUTCDATETIME()` cho thời điểm kiểm tra. Adapter hiện tại kế thừa clock `SYSDATETIME()` theo giờ server; override chỉ tác động freshness.

`ModifiedDate` là thời điểm sửa bản ghi nghiệp vụ, **không phải thời điểm ingest hay restore database**. Các timestamp không kèm timezone hiện được diễn giải là UTC. Nguồn mới dùng timezone khác phải được chuyển đổi trước khi so sánh.

Restore file AdventureWorks hôm nay không làm dữ liệu nghiệp vụ năm 2014 trở thành mới. Không đổi timestamp nguồn, không dịch đồng hồ và không tăng ngưỡng lên nhiều năm để làm xanh kết quả. Khi có ingestion thật, nhóm nên ghi thời điểm nạp/heartbeat đáng tin cậy và chọn SLA phù hợp. Ngay cả dữ liệu hợp lệ cũng có thể không đạt yêu cầu độ mới.

Freshness dùng `MAX(ModifiedDate)`, vì vậy cần kết hợp timestamp tests:

| Tình huống fixture | Freshness | Timestamp tests |
| --- | --- | --- |
| Mới 1 giờ | PASS | PASS |
| Cũ 36 giờ | WARN | PASS |
| Cũ 72 giờ | ERROR | PASS |
| Một dòng NULL | ERROR | `not_null` FAIL, 1 dòng |
| Ngày tương lai 24 giờ | PASS do tuổi âm | `no_future_dates` FAIL, 1 dòng |
| Một dòng mới và một dòng NULL | PASS do MAX bỏ qua NULL | `not_null` FAIL, 1 dòng |
| Bảng rỗng | ERROR | Cả hai tests PASS vì không có dòng vi phạm |

Ở dbt 1.8 đang chạy, NULL/empty `MAX` được biểu diễn thành ngày `0001-01-01` và freshness ERROR; không nhầm đây với lỗi SQL. Warning-only trả exit 0, bộ có stale trả exit 1. Fixtures kiểm tra cả status lẫn exit code, không chỉ tìm chữ PASS trong log.

## Chạy lại trên PowerShell

Điều kiện: Docker hoạt động, `sqlserver`/`dbt` đã chạy, AdventureWorks2014 đã restore và profile local hợp lệ. Thực thi tại thư mục gốc repo. **Chạy tuần tự**, vì `dbt deps` thay đổi chung thư mục `dbt_packages`.

```powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
$evidence = "docs/evidence/tuan-week2-day6-7/$stamp"
.\scripts\verify_dbt_baseline.ps1 -OutputDirectory "$evidence/baseline"
.\scripts\verify_dbt_freshness.ps1 -OutputDirectory "$evidence/freshness"
$freshnessExit = $LASTEXITCODE
Write-Host "Freshness gate exit code: $freshnessExit"
```

Freshness runner thực hiện `deps → timestamp tests → source freshness`, lưu riêng `timestamp_tests.run_results.json`, `sources.json`, stdout và `freshness_status.json`. Kiểm tra chính xác 12 test IDs và 6 source IDs; không dùng artifact cũ. Trạng thái và mã thoát:

- **0**: timestamp hợp lệ, freshness PASS hoặc WARN.
- **1**: timestamps không hợp lệ hoặc nguồn quá hạn. Dataset lịch sử hiện cho `status: stale`, exit 1.
- **2**: lỗi thực thi hoặc artifact không hợp lệ; không được coi là stale dự kiến.

Muốn thay SLA đã thống nhất, dùng `-WarnAfterHours 12 -ErrorAfterHours 24`. Các ngưỡng wrapper nhận là số nguyên giờ dương, tối đa 8760, với warn nhỏ hơn error. Chọn thư mục output mới mỗi lần; runner không ghi đè evidence.

Chạy fixture trên chính macro/YAML hiện tại (không sửa bảng nghiệp vụ):

```powershell
docker compose cp scripts/verify_dbt_test_contracts.py dbt:/tmp/verify_dbt_test_contracts.py
if ($LASTEXITCODE -ne 0) { throw 'Copy logging helpers failed' }
docker compose cp scripts/verify_dbt_freshness_contracts.py dbt:/tmp/verify_dbt_freshness_contracts.py
if ($LASTEXITCODE -ne 0) { throw 'Copy fixture runner failed' }
$fixtureOutput = "/tmp/tuan-freshness-$stamp"
docker compose exec -T dbt python /tmp/verify_dbt_freshness_contracts.py --project-dir /usr/app/dbt --output-dir $fixtureOutput
$fixtureExit = $LASTEXITCODE
docker compose cp "dbt:$fixtureOutput" "$evidence/contracts"
if ($LASTEXITCODE -ne 0) { throw 'Copy fixture evidence failed' }
if ($fixtureExit -ne 0) { throw 'Fixture verification failed; inspect summary.json and stdout' }
```

Runner Python tái sử dụng helpers ghi log của script tuần 1 nên cần copy cả hai files. Nó tạo 7 views trong schema UUID `tuan_freshness_contracts_*`, từ chối schema đã tồn tại, chỉ xóa các views của fixture và xác minh cleanup. Policy được đọc từ source YAML thật; macro UTC và `no_future_dates` cũng được copy từ project thật. Output ghi SHA-256 để truy vết.

## Bàn giao

Phần triển khai và kiểm thử ngày 6–7 đã hoàn tất. **Dữ liệu mẫu vẫn stale**, và đây là phát hiện chất lượng cần giữ khi demo, không phải tiêu chí bị bỏ qua.

Freshness là lệnh riêng, không tự chạy trong `dbt run`/`dbt test`/`dbt build`. Handoff cho Bảo/Thịnh: khi có nguồn được cập nhật và SLA được chốt, chạy timestamp tests rồi `dbt source freshness` trước downstream, giữ nguyên exit code và artifacts. Các workflow CI hiện tại chạy 200 data tests khi nhận thay đổi này; chưa bổ sung một freshness gate bắt buộc lên dataset lịch sử trong PR này.

Việc tiếp theo của Tuân: ngày 8–9, cấu hình Great Expectations với customer/order suites và checkpoint.

Tham khảo: [dbt freshness properties và thay đổi cú pháp theo phiên bản](https://docs.getdbt.com/reference/resource-configs/freshness), [sources.json](https://docs.getdbt.com/reference/artifacts/sources-json). Tài liệu online hiện mô tả cả dbt mới hơn; cú pháp, mã thoát và hành vi NULL ở báo cáo này đã được kiểm chứng bằng runtime 1.8.7.
