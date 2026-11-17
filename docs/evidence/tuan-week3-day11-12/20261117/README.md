# Tuân — bằng chứng tuần 3, ngày 11–12

Kết quả: **đạt phạm vi tích hợp GE–Airflow, tests và dbt docs của ngày 11–12**. Đây là nghiệm thu local trên AdventureWorks2014, chưa phải nghiệm thu toàn bộ tuần 3 hoặc triển khai production.

## Lượt chạy dữ liệu thật

DAG `dbt_transform`, run `tuan-week3-day11-12-20261117-01`, được trigger thủ công và chạy bằng scheduler với LocalExecutor. Bắt đầu `2026-11-17T01:48:10.674063+00:00`, kết thúc `2026-11-17T01:53:21.892028+00:00` (08:48–08:53 giờ Việt Nam).

- Năm tasks `dbt_deps → dbt_run → dbt_test → ge_validate → dbt_docs` đều success lần đầu, native/final exit đều 0.
- 10 models thành công; 200 dbt tests PASS, tập test IDs không thay đổi so với ngày 10.
- Customer checkpoint: 10 expectations PASS trên 19.820 dòng. Order checkpoint: 30 expectations PASS trên 121.317 dòng.
- Catalog và manifest khớp đủ 10 models/131 cột được mô tả, 6 nguồn/59 trường được mô tả; bốn project macros và arguments có tài liệu.

## Bài thử lỗi

Bốn contracts đều đạt, chạy từ `01:55:08` đến `01:59:37` UTC. Ba case đầu dùng chính operators GE/docs qua `DAG.test()` với retries=0; một case gọi lại helper cùng context để kiểm tra bảo toàn artifacts. Fixtures dùng schema UUID riêng; cleanup đã xác nhận và tiến trình quản lý exit 0.

| Case | Kết quả |
| --- | --- |
| Dữ liệu hợp lệ | GE exit 0, cả GE/docs success; 40 checks đạt |
| Dữ liệu sai | GE exit 1, đúng bốn domain rules thất bại; docs upstream_failed và không thực thi |
| Thiếu bảng order | GE exit 2, docs upstream_failed và không thực thi |
| Gọi lại helper sau lỗi | Thêm một attempt mới; tất cả hashes của bằng chứng cũ giữ nguyên |

## Đọc hồ sơ

| File | Nội dung |
| --- | --- |
| [acceptance.json](acceptance.json) | Kết quả tổng hợp và phạm vi/giới hạn |
| [runtime.json](runtime.json) | Phiên bản runtime, image ID và trạng thái services trước lượt chạy |
| [full_dag.json](full_dag.json) | Trạng thái DagRun/task instances lấy từ metadata Airflow sau khi kết thúc |
| [task_summaries.json](production/task_summaries.json) | Exit codes, timestamps và runner hash của năm tasks |
| [dbt_run.run_results.json](production/dbt_run.run_results.json) | Kết quả 10 models |
| [dbt_test.run_results.json](production/dbt_test.run_results.json) | Kết quả 200 tests |
| [GE summary](production/ge/summary.json) | Kết quả tổng hợp 40 expectations |
| [customer checkpoint](production/ge/customer_checkpoint.json), [order checkpoint](production/ge/order_checkpoint.json) | Kết quả từng checkpoint, không chứa danh sách dòng khách hàng lỗi |
| [docs_coverage.json](docs_coverage.json) | Đối chiếu catalog/manifest, danh sách cột và test IDs digest |
| [contracts/summary.json](contracts/summary.json) | Assertions, Airflow states, exit codes và cleanup của bốn bài thử |
| [contracts/case_reports.json](contracts/case_reports.json) | Task summaries và GE reports của từng case |
| [provenance.json](provenance.json) | SHA-256 của artifacts gốc và code/config đã dùng |

JSON được chuẩn hóa UTF-8/LF khi đóng gói. `raw_source_artifact_sha256` tham chiếu bytes của bản gốc local trong `great_expectations/uncommitted/`; không dùng các hash này để so với bản JSON đã định dạng lại. Code chạy qua Windows bind mounts có thể dùng CRLF: `executed_worktree_sha256` đối chiếu bytes lúc chạy, `canonical_lf_sha256` đối chiếu Git blob sau chuẩn hóa LF.

Manifest/catalog/index HTML lớn và stdout logs được giữ local tại `great_expectations/uncommitted/airflow/6c09a9980aff0cf8ba25/`; các hash tương ứng nằm trong provenance/coverage. Hướng dẫn tái chạy và xem dbt docs: [tích hợp Airflow](../../../tuan_week3_day11_12.md), [dbt docs](../../../tuan_week3_dbt_docs.md).

## Giới hạn còn lại

- Freshness không chạy trong DAG này. `DQ-W2-01` của sáu nguồn lịch sử vẫn mở theo [nghiệm thu tuần 2](../../../tuan_week2_quality_report.md).
- Các bài thử lỗi xác nhận operators và dependencies qua `DAG.test()`; chưa kiểm chứng lịch chạy định kỳ, thời gian retry của scheduler, notifications hoặc monitoring của nhóm.
- Gọi lại helper xác nhận không ghi đè artifacts; chưa kiểm chứng cưỡng bức hủy/timeout và dọn tiến trình bên trong container.
- CI hiện tại kiểm tra Python/SQL và dbt; chưa tự chạy bộ GE–Airflow local này.
