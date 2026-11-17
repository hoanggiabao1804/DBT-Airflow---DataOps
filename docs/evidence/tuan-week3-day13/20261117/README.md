# Tuân — nghiệm thu ngày 13, tuần 3

Kết quả: **đạt phạm vi đối chiếu Bronze → Silver → Gold và test coverage**. Báo cáo đầy đủ và hướng dẫn chạy lại: [ngày 13](../../../tuan_week3_day13.md).

## Các lượt kiểm chứng

| Thành phần | Thời gian UTC, ngày 17/11/2026 | Kết quả |
| --- | --- | --- |
| Fixtures SQL | 07:17:07–07:17:23 | 27/27 đạt: 5 baseline, 17 mutations được phát hiện, 5 baseline sau rollback; cleanup xác nhận |
| DAG scheduler/LocalExecutor | 07:27:15–07:32:13 | 5 tasks success lần đầu, native/final exits đều 0; 10 models, 202 tests, GE 40 checks, docs generate |
| Đọc đối chiếu sau DAG | 07:32:35–07:32:38 | Transaction SERIALIZABLE, 20/20 kiểm tra đạt; 6 SQL đối chiếu có 0 vi phạm |

Giờ Việt Nam = UTC + 7. Dữ liệu lab AdventureWorks2014; không sửa dữ liệu nguồn. Lượt đọc sau DAG có transaction riêng, không khẳng định là cùng snapshot với build/test. Fixtures chỉ dùng bảng tạm theo connection, không sửa Silver/Gold thật.

## File bằng chứng

| File | Nội dung |
| --- | --- |
| [acceptance.json](acceptance.json) | Phạm vi đạt và giới hạn |
| [full_dag.json](full_dag.json) | DagRun/task states lấy từ metadata Airflow |
| [runtime.json](runtime.json) | Container image IDs và trạng thái services sau DAG |
| [layer_reconciliation.json](layer_reconciliation.json) | Inventory nguồn/models, bộ lọc Silver, số đơn/số lượng/doanh thu, 20 kết quả và hashes SQL |
| [test_coverage.json](test_coverage.json) | Manifest/results cùng invocation; 202 IDs, 196 generic + 6 singular, danh sách cột và nguồn; baseline thêm 2, xóa 0 |
| [reconciliation_contracts.json](reconciliation_contracts.json) | 27 assertions với mismatch counts, rollback/cleanup và hashes SQL đã chạy |
| [production/task_summaries.json](production/task_summaries.json) | Bằng chứng năm task attempts, timestamps và native/final exit codes |
| [dbt run results](production/dbt_run.run_results.json) | 10 model results |
| [dbt test results](production/dbt_test.run_results.json) | 202 test results, không WARN/FAIL/ERROR/SKIP |
| [GE summary](production/ge/summary.json) | 40 expectations PASS trên Silver thật |
| [customer checkpoint](production/ge/customer_checkpoint.json), [order checkpoint](production/ge/order_checkpoint.json) | Kết quả tổng hợp từng checkpoint |
| [provenance.json](provenance.json) | SHA-256 artifacts gốc và code/config dùng để chạy |

Các artifacts nguyên bản nằm local tại `great_expectations/uncommitted/airflow/d679e31b4e77affd8496/`, `day13-reconciliation-20261117-01/`, `day13-contracts-20261117-01.json`, `day13-coverage-20261117-01.json`. Manifest/catalog/index HTML lớn và stdout logs giữ local; hồ sơ lưu hashes để đối chiếu. JSON được định dạng lại thành UTF-8/LF khi đóng gói nên hash nguồn nguyên bản có thể khác hash bản công bố. Code trên Windows bind mounts có thể có CRLF; `canonical_lf_sha256` cho phép so với Git blob sau chuẩn hóa newline.

## Diễn giải và giới hạn

- 121.317 là dòng hàng, 31.465 mới là số đơn hàng phân biệt. Tổng số lượng 274.914 và doanh thu decimal `109846381.399888` khớp xuyên tầng. Không cộng số đơn theo sản phẩm thành số đơn toàn kỳ.
- 10/10 models có generic tests; 86/131 cột có generic column-level test. Không diễn giải đây là tỷ lệ bao phủ nghiệp vụ hoặc chất lượng dữ liệu. GE/singular tests và các cột optional được phân tích riêng trong báo cáo ngày 13.
- Hai tests dimension mới bảo toàn tập khóa, chưa đối chiếu mọi thuộc tính dimension. Inventory nguồn không chứng minh toàn bộ values hệ thống nguồn → Bronze đã được kiểm toán.
- GE chỉ áp dụng Silver customer/order; 40 expectations không phải 40 quy tắc độc lập bổ sung vào 202 dbt nodes.
- Freshness không được chạy lại; `DQ-W2-01` của sáu nguồn lịch sử vẫn mở. Chưa nghiệm thu failure/retry/alert, cleanup tiến trình sau timeout hoặc deployment chung của nhóm.
