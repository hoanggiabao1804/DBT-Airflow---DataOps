# Great Expectations — customer và order

Phần ngày 8–9 của Tuân: hai suites kiểm tra toàn bộ bảng Silver và hai checkpoint chạy bằng SQL Server. Great Expectations **0.18.22** sử dụng định dạng suites/checkpoints của bài lab; dependencies chạy trong container `ge` riêng. Không cài chung các phiên bản này vào dbt hoặc Airflow.

[Báo cáo chất lượng kết thúc tuần 2](../docs/tuan_week2_quality_report.md) tổng hợp kết quả dbt, freshness, GE và bàn giao sang tuần 3.

| Checkpoint | Suite | Bảng mặc định | Số điều kiện |
| --- | --- | --- | --- |
| `customer_checkpoint` | `customer_suite` | `silver.slvr_customers` | 10 |
| `order_checkpoint` | `order_suite` | `silver.slvr_sales_orders` | 30 |

Customer: đủ cột, bảng không rỗng, khóa không NULL/không trùng, các trường tên không NULL, miền `email_promotion`, timestamp không tương lai. `Unknown` và email preference NULL vẫn hợp lệ; suite không kiểm tra định dạng/trim tên.

Order: đủ cột, bảng không rỗng, khóa ghép `(sales_order_id, order_detail_id)`, các cột bắt buộc, số lượng dương, giá/doanh thu không âm, discount trong `[0,1]`, miền status/channel/discount flag và timestamp. Một đơn có nhiều dòng là hợp lệ; giá 0, discount 100%, ngày giao dự kiến trong tương lai và ship date NULL đều hợp lệ.

Suites này bổ sung lớp kiểm tra dữ liệu đầu ra Silver. Các phép đối chiếu, khóa ngoại và công thức doanh thu vẫn được kiểm tra trong dbt. Freshness có lệnh riêng và vẫn báo quá hạn trên dữ liệu AdventureWorks lịch sử.

## Chạy trên máy hiện tại

Chạy tại thư mục gốc repository. Cần Docker đang hoạt động, SQL Server đã restore AdventureWorks2014, models dbt đã được build và `dbt/profiles.yml` có target SQL-auth hợp lệ. Script chỉ đọc target được chọn; mật khẩu không đưa vào command line hay báo cáo. Container dùng ODBC Driver 17.

```powershell
docker compose -f docker-compose.yml -f docker-compose.ge.yml --profile quality build ge
if ($LASTEXITCODE -ne 0) { throw 'GE image build failed' }

$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
docker compose -f docker-compose.yml -f docker-compose.ge.yml --profile quality run --rm --no-deps ge --target dev --schema silver --output-dir "/evidence/$stamp"
$validationExit = $LASTEXITCODE
Write-Host "GE exit code: $validationExit"
```

Đọc `great_expectations/uncommitted/<stamp>/summary.json` và từng `<checkpoint>.json`. Output cũ không bị ghi đè. Khi dùng Bash, đặt `stamp=$(date -u +%Y%m%dT%H%M%SZ)` rồi sử dụng cùng lệnh Compose; kiểm tra `$?` ngay sau lệnh.

- Exit **0**: mọi checkpoint được chọn đều PASS.
- Exit **1**: dữ liệu vi phạm ít nhất một expectation.
- Exit **2**: lỗi thực thi/cấu hình (kết nối, thiếu bảng, target/schema sai hoặc output đã tồn tại).

Để chạy riêng customer, thêm `--checkpoint customer_checkpoint`; tương tự cho `order_checkpoint`. Mặc định luôn chạy cả hai. Không thêm `|| true` hoặc bỏ qua exit code khi dùng như quality gate.

`--target` chọn connection từ dbt profile; `--schema` là **schema vật lý của các models Silver**, không phải schema mặc định của profile. Với môi trường khác, truyền đúng schema và các biến mà target đó dùng qua `docker compose run -e VARIABLE_NAME ...`; không ghi mật khẩu vào file được commit. Runner hiện hỗ trợ SQL authentication. Validation yêu cầu quyền SELECT; bộ fixture bên dưới cần quyền tạo/xóa schema riêng.

## Kiểm chứng dữ liệu sai

```powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
docker compose -f docker-compose.yml -f docker-compose.ge.yml --profile quality run --rm --no-deps --entrypoint python ge /workspace/scripts/verify_ge_contracts.py --target dev --output-dir "/evidence/contracts-$stamp"
if ($LASTEXITCODE -ne 0) { throw 'GE contract verification failed; inspect summary.json' }
```

Fixture dùng bảng tổng hợp trong schema UUID `ge_contracts_*`; không cập nhật bảng Silver. Nó chạy chính suites/checkpoints đã commit, kiểm tra các trường hợp hợp lệ, dữ liệu sai, bảng rỗng và lỗi thiếu bảng, rồi xác minh schema đã được dọn bằng connection mới. Runner fixture chỉ trả 0 khi kết quả và mã thoát đều đúng kỳ vọng, bao gồm những lần checkpoint phải FAIL.

## Cấu hình và bàn giao

- `great_expectations.yml`: SQL datasource, hai table assets, stores; connection/schema qua biến môi trường do runner cấp.
- `expectations/*.json`: 40 điều kiện, mỗi điều kiện có `meta.rule_id` để đọc kết quả và kiểm thử chính xác.
- `checkpoints/*.yml`: checkpoint gọi suite tương ứng và `StoreValidationResultAction`.
- `scripts/run_ge_checkpoints.py`: tạo context tạm, thực thi checkpoint thật, kiểm tra đủ bộ rules và xuất kết quả tổng hợp cùng SHA-256 của cấu hình.

Native GX validation store tồn tại trong context tạm của mỗi lần chạy; sau đó runner giữ lại kết quả tổng hợp cần thiết trong output và xóa context tạm. Báo cáo không chứa tên khách, các dòng lỗi, connection string hay mật khẩu. Telemetry và progress bars đã tắt. Chưa dựng Data Docs HTML ở bước này.

Container mặc định chạy theo yêu cầu, không chạy nền. Airflow/CI có thể gọi runner và dùng exit code 0/1/2; việc tích hợp DAG thuộc phần tiếp theo theo kế hoạch nhóm. Chưa thay đổi các workflow hay DAG hiện tại.

Tham khảo API được dùng: [GX 0.18 SQL datasource](https://docs.greatexpectations.io/docs/0.18/oss/guides/connecting_to_your_data/fluent/database/connect_sql_source_data/), [GX 0.18 checkpoints](https://docs.greatexpectations.io/docs/0.18/oss/get_started/get_started_with_gx_and_sql/), [package 0.18.22](https://pypi.org/project/great-expectations/0.18.22/). Đây là phiên bản tương thích bài lab, không phải tuyên bố về phiên bản GX mới nhất.
