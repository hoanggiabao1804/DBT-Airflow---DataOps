# Tuân — bằng chứng chạy thử demo ngày 15

**Chạy thử kỹ thuật đạt**, ngày **19/11/2026**, run `tuan-day15-20261119-01`, code `2971267df716f220f78ab047f9a91c0428effa66` (develop sau PR #16). Mô hình và bộ kiểm tra không đổi; phần ngày 15 bổ sung kịch bản trình bày và bằng chứng thực thi mới. Xem [hướng dẫn demo 12 phút](../../../tuan_week3_day15_demo.md).

Các lệnh được chạy **thủ công, tuần tự** trên ba services `sqlserver`, `dbt`, `ge-worker`. Airflow scheduler/webserver đang dừng trong lần này. Đây không phải lượt DAG mới; bằng chứng scheduler trước đó ở [ngày 13](../../tuan-week3-day13/20261117/README.md). Hồ sơ cũng không xác nhận đã trình bày trước nhóm/giảng viên: Tuân vẫn cần thực hiện phần nói và trả lời câu hỏi.

## Các phần đã chạy

Toàn lượt: **13:00:59–13:11:37 UTC**, tương đương **20:00:59–20:11:37 giờ Việt Nam**. Thời gian khởi động Docker/services nằm ngoài khoảng này. Các mốc trong bảng là thời gian lệnh bắt đầu/kết thúc được lưu trong [rehearsal.json](rehearsal.json).

| Thành phần | Thời gian UTC | Kết quả |
| --- | --- | --- |
| dbt deps | 13:01:07–13:02:26 | Exit 0 |
| dbt run | 13:02:26–13:03:22 | 10 models success: 4 views, 6 tables |
| dbt test | 13:03:22–13:06:33 | 202 PASS; không WARN/FAIL/ERROR/SKIP; đủ tập IDs của manifest |
| GE trên Silver thật | 13:06:33–13:08:03 | Customer 10/10, order 30/30; native exit 0 |
| dbt docs generate | 13:08:03–13:08:49 | Exit 0; 10 models, 131 cột có mô tả và khớp catalog |
| Đối chiếu đọc dữ liệu | 13:08:49–13:09:01 | 20/20 kiểm tra; sáu SQL đối chiếu không có dòng vi phạm |
| Generic dbt fixtures | 13:09:02–13:09:28 | 8/8 assertions: 4 tests PASS + 4 FAIL dự kiến, native dbt test exit 1; verifier exit 0; cleanup đạt |
| Reconciliation fixtures | 13:09:28–13:09:30 | 27/27 assertions: 5 baseline + 17 mutations bị phát hiện + 5 baseline sau rollback; cleanup đạt |
| GE fixtures | 13:09:30–13:11:37 | 8/8 tình huống đúng kỳ vọng, kiểm chứng native CLI exit 0/1/2; cleanup đạt |

Fixtures dùng schema UUID hoặc bảng tạm theo connection. Lỗi được tạo có chủ đích trong các bảng này; không sửa Silver thật để làm demo lỗi. Verifier chỉ PASS khi validation trả đúng kết quả dự kiến và dọn fixture thành công. Không cộng số ca fixture vào 202 dbt tests trên dữ liệu thật.

## Mở bằng chứng nào khi trình bày

| File | Điều cần chỉ |
| --- | --- |
| [acceptance.json](acceptance.json) | Tóm tắt kết quả, commit/run, trạng thái chưa ghi nhận demo trước người nghe |
| [rehearsal.json](rehearsal.json) | Các lệnh và mã thoát thật theo thứ tự, thời gian, đường dẫn stdout local |
| [runtime.json](runtime.json) | Image IDs, ba services chạy và Airflow dừng; chụp sau rehearsal, không phải health/SLA tổng thể |
| [dbt run](production/dbt_run.run_results.json), [dbt test](production/dbt_test.run_results.json) | Kết quả từng node và invocation ID |
| [test_coverage.json](test_coverage.json) | 196 generic + 6 singular; 202 test IDs không đổi so với ngày 13; không thiếu/thừa/trùng kết quả |
| [GE summary](production/ge/summary.json), [customer](production/ge/customer_checkpoint.json), [order](production/ge/order_checkpoint.json) | 40 rule IDs, counts và trạng thái validation |
| [layer_reconciliation.json](layer_reconciliation.json) | 20 kiểm tra, grain, số lượng/doanh thu và số đối tượng chưa giao dịch |
| [docs_coverage.json](docs_coverage.json) | 10 models/131 cột có mô tả, catalog và SQL khớp; HTML tồn tại, không phải bản ghi thao tác trình duyệt |
| [Generic summary](generic_contracts/summary.json), [generic test results](generic_contracts/test.run_results.json) | 4 PASS/4 FAIL dự kiến, số vi phạm 2/3/2/3, native test exit 1 và cleanup |
| [Reconciliation fixtures](reconciliation_contracts.json) | 27 assertions, lỗi KPI/tập khóa được phát hiện, rollback và cleanup |
| [GE fixture summary](ge_contracts/summary.json) | 8 tình huống, expected/actual, `native_cli`, cleanup |
| [GE hợp lệ](ge_contracts/valid_nullable_free_discount_multiline.json), [bảng rỗng](ge_contracts/empty_tables.json), [thiếu bảng](ge_contracts/missing_table_runtime_error.json) | Ba native CLI exits 0, 1, 2; phân biệt dữ liệu vi phạm với lỗi thực thi |
| [provenance.json](provenance.json) | Hash artifacts nguyên bản, 47 file code/config và bản JSON công bố |

Số liệu đối chiếu mới: **19.820 customers, 504 products, 121.317 dòng hàng, 31.465 đơn, quantity 274.914**, doanh thu decimal `109846381.399888`. Gold daily có 1.124 dòng; Gold giữ 701 khách hàng và 238 sản phẩm chưa giao dịch. Không cộng số đơn theo sản phẩm thành số đơn toàn kỳ. Transaction đọc đối chiếu là `SERIALIZABLE` từ **13:08:58–13:09:00 UTC**, sau dbt run/test; không phải snapshot chung với các bước trước.

## Nguồn artifacts và giới hạn

- Dữ liệu raw local: `great_expectations/uncommitted/day15-20261119-01/` và `dbt/target/tuan-day15-20261119-01/`; không ghi đè bằng chứng ngày 13/14.
- Manifest, catalog, index HTML và stdout đầy đủ giữ local ignored. JSON công bố được định dạng UTF-8/LF, nên hash khác raw bytes là bình thường. Code dùng hash raw và hash chuẩn hóa LF; Git có vài file legacy lưu CRLF nên cả hai phía đều chuẩn hóa khi so sánh.
- Cùng invocation của bước `test` được dùng cho coverage và reconciliation; không ghép manifest của bước `docs` với results của `test`. Docs có invocation riêng.
- GE chỉ kiểm tra Silver customer/order. 202 dbt tests + 40 expectations có phần trùng mục đích; PASS không chứng minh toàn bộ nghiệp vụ hay mọi cột đã được kiểm thử. 86/131 cột có generic test trực tiếp là inventory, không phải tỷ lệ dữ liệu đúng.
- **Freshness `DQ-W2-01` vẫn OPEN**; không chạy lại freshness trong rehearsal này. Timestamp lịch sử không được sửa, SLA 24/48 giờ không đổi.
- Phần demo, monitoring/incident, deploy/rollback và nghiệm thu chung của nhóm không được thay thế bởi hồ sơ chạy thử riêng của Tuân. Sau buổi trình bày thật mới bổ sung ngày giờ/người tham dự và ghi nhận hoàn thành phần demo trước người nghe.
