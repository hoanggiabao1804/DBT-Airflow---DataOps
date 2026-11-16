# Bằng chứng Great Expectations ngày 8–9

Ngày chạy: **16/11/2026**, Asia/Saigon; thời gian trong JSON là UTC.

- `baseline/summary.json`: hai checkpoint trên SQL Server thật, 19.820 customers và 121.317 order lines, 40/40 expectations PASS, exit 0. Hai JSON theo checkpoint giữ kết quả từng suite.
- `contracts/summary.json`: 8 tình huống đều khớp kỳ vọng, gồm dữ liệu hợp lệ, 6 nhóm dữ liệu vi phạm và lỗi thiếu bảng; schema fixture đã được xác minh dọn sạch. Mỗi thư mục case giữ summary với kết quả từng rule và hash cấu hình.
- `contracts/*.stdout.txt`: stdout của ba lần gọi CLI thật, kiểm tra exit 0/1/2. Các case khác gọi cùng hàm runner trực tiếp.
- `runtime.json`: các phiên bản Python, package và ODBC của image đã build.

JSON là kết quả tổng hợp xuất trực tiếp từ checkpoint thật, không chứa dữ liệu khách hàng hay connection string. Artifacts `.stdout.log` gốc chỉ được đổi đuôi thành `.stdout.txt` khi sao chép vào Git. Native GX validation stores tạm không được đưa vào repository.

Case `missing_table_runtime_error` chạy sau case bảng rỗng: customer nonempty vẫn FAIL, sau đó bảng order bị bỏ trong **schema fixture** nên checkpoint order trả lỗi thực thi. Exit 2 được ưu tiên và khớp kỳ vọng; đây không phải kết quả trên bảng Silver thật.

Hướng dẫn chạy lại: [Great Expectations README](../../../../great_expectations/README.md). Diễn giải và phạm vi: [báo cáo ngày 8–9](../../../tuan_week2_day8_9.md).
