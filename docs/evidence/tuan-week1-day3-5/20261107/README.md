# Bằng chứng Tuân — Tuần 1, ngày 3–5

Ngày thực hiện: **07/11/2026**, múi giờ Asia/Saigon (UTC+7). Timestamp trong artifacts có hậu tố UTC/Z dùng giờ UTC. [Báo cáo công việc](../../../tuan_week1_day3_5.md).

**Kết quả sau sửa đã xác minh:** baseline passed với 10/10 models và **188/188 tests PASS**; 3/3 Gold fixture checks PASS; 8/8 generic fixture cases khớp kỳ vọng và cleanup đã được xác nhận. Baseline hoàn tất lúc **16:31:10** ngày 07/11/2026 (Asia/Saigon). Các FAIL trước sửa và FAIL cố tình tạo trong generic fixtures được lưu để chứng minh tests phát hiện lỗi.

| Artifact | Ý nghĩa |
| --- | --- |
| [`deps.stdout.txt`](deps.stdout.txt) | Cài dbt dependencies trước khi chạy tests đối chiếu ban đầu. |
| [`reconciliation.before.stdout.txt`](reconciliation.before.stdout.txt) | Log của 4 singular tests trên kết quả models trước sửa. |
| [`reconciliation.before.run_results.json`](reconciliation.before.run_results.json) | 2 PASS (Silver, product), 2 FAIL (daily: 421 dòng; customer: 15.913 dòng). Exit 1 là bằng chứng tests phát hiện các lỗi KPI thực tế. Product PASS trên dữ liệu hiện tại không loại trừ lỗi chia cho 0 khi xuất hiện đơn miễn phí. |
| [`gold_contracts.before.json`](gold_contracts.before.json) | SQL Gold trước sửa chạy trên bảng tạm: customer sai AOV/số đơn giảm giá; daily sai số đơn online; product gặp lỗi SQL Server 8134 chia cho 0. |
| [`gold_contracts.after.json`](gold_contracts.after.json) | **3/3 models passed**, mọi danh sách mismatches đều rỗng. Cùng các tình huống kiểm thử, dùng SQL Gold sau sửa; chứa hash từng SQL model. |
| [`baseline/baseline_status.json`](baseline/baseline_status.json) | **passed**; `deps`, `debug`, `run`, `test` đều exit 0. Ghi thời gian và xác nhận artifacts RUN/TEST đúng lệnh. |
| [`baseline/run.run_results.json`](baseline/run.run_results.json) | **10/10 models success**, không ERROR/SKIP. |
| [`baseline/test.run_results.json`](baseline/test.run_results.json) | **188/188 tests PASS**, không FAIL/ERROR/WARN/SKIP. Cả 4 singular tests đối chiếu có failures = 0. |
| [`baseline/model_relations.json`](baseline/model_relations.json) | Tên database/schema/relation lấy từ manifest của đúng lần baseline này. |
| [`generic_contracts/summary.json`](generic_contracts/summary.json) | **passed**, cả 8 cases có matched = true; `contracts_verified` và `cleanup_verified` đều true. Các stdout/run results và dữ liệu fixture nằm cùng thư mục. |

Baseline dùng thư mục log/target mới trong container, tách kết quả RUN khỏi TEST. Không dùng artifacts cũ trong `dbt/target` để chứng minh lần chạy này. Bằng chứng ngày 1–2 trong thư mục riêng được giữ nguyên.

Các JSON được định dạng với indent 2 và sắp xếp keys; logs bỏ khoảng trắng cuối dòng. Files dùng UTF-8 không BOM và xuống dòng LF để phù hợp kiểm tra repository. Giá trị JSON, nội dung thông báo, timestamp và kết quả kiểm thử được giữ nguyên.

Generic fixture suite thực tế có **4 cases PASS và 4 cases FAIL đúng chủ đích**. Các cases không hợp lệ có đúng số dòng lỗi theo định nghĩa trong runner (2/3/2/3); `dbt test` exit 1 là kỳ vọng của bộ fixture này. Kết quả tổng hợp xác nhận toàn bộ trạng thái/số dòng lỗi đúng; lệnh kiểm tra từ connection mới cũng xác nhận schema fixture đã được dọn xong.

Gold fixture suite dùng các bảng `#temporary` trong một connection, kiểm tra đơn nhiều dòng, đơn miễn phí, khách và sản phẩm chưa có giao dịch. Bảng tạm tự mất khi connection đóng; không ghi lên các bảng nguồn hoặc bảng Gold đang dùng.

Phạm vi bao gồm đủ 10 models và 6 bảng nguồn được sử dụng; project còn 7 source declarations chưa dùng, không được tính là đã có test coverage. Các bằng chứng này xác nhận phạm vi dbt của Tuân. Không suy ra Airflow end-to-end hoặc GitHub CI bắt buộc đã hoàn tất từ kết quả chạy local. Xem lệnh chạy lại và phần bàn giao trong [báo cáo](../../../tuan_week1_day3_5.md).
