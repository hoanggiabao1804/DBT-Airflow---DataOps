# Tuân — Tuần 3, ngày 11–12: GE trong Airflow và dbt docs

Phạm vi theo `Project-Devops.md`: tích hợp Great Expectations với Airflow, hoàn thiện tests và dbt docs. DAG `dbt_transform` thực thi tuần tự:

```text
dbt_deps → dbt_run → dbt_test → ge_validate → dbt_docs
```

`ge_validate` chạy cả customer/order checkpoints đã hoàn thành tuần 2. Exit 1 (dữ liệu không đạt) và exit 2 (lỗi thực thi) đều làm task thất bại; downstream yêu cầu `all_success`. Không có nhánh thành công giả hoặc bỏ qua lỗi. Task có một retry sau một phút; mỗi lần thử giữ bằng chứng riêng. `max_active_runs=1` tránh hai lượt của DAG cùng ghi dbt models/packages.

Giới hạn vận hành: chưa kiểm chứng hủy task/timeout cưỡng bức. Khi dừng client `docker exec`, tiến trình trong container có thể vẫn chạy; cần kiểm tra và dừng tiến trình cũ trước khi clear/retry thủ công trong tình huống này. Bằng chứng retry bên dưới xác nhận không ghi đè artifacts, không xác nhận cleanup tiến trình sau timeout. Phần xử lý tình huống này bàn giao cùng Thịnh khi kiểm thử failure/retry ngày 13.

## Runtime và phạm vi cấu hình

- Airflow 2.7.1 giữ nguyên phiên bản của project; image chỉ bổ sung Docker CLI 27.5.1. Bỏ cài dbt/provider không pin trong Airflow vì dbt và GX đã có môi trường riêng.
- `dbt` chạy dbt 1.8.7; `ge-worker` dùng image GX 0.18.22 hiện có. Worker GE chờ lệnh, không tự lên lịch; Airflow gọi runner bằng `docker exec`.
- Runner tìm container qua Compose project/service labels, không hardcode tên container. Profile SQL Server được đọc từ file mount; password không truyền trong command line hoặc Airflow task env.
- Overlay `docker-compose.airflow-quality.yml` bổ sung init idempotent, health checks và mounts. File Compose gốc giữ nguyên. Đây là cấu hình lab, kế thừa tài khoản demo của project.
- DAG mặc định chạy theo trigger thủ công. Có thể cấu hình `DATAOPS_SCHEDULE` trên **cả webserver/scheduler** khi Thịnh chốt lịch; `catchup=False`. Việc tự động nối các bước trong một DAG đã có, khác với bật lịch định kỳ.
- Sáu nguồn lịch sử vẫn không đạt freshness SLA (`DQ-W2-01`). DAG không chạy freshness thành một gate luôn thất bại trên AdventureWorks2014 và không tuyên bố đã đạt SLA. Chính sách freshness được giữ trong [báo cáo tuần 2](tuan_week2_quality_report.md).

## Khởi động và chạy

Chạy tại gốc repository, sau khi SQL Server đã restore AdventureWorks2014 và `dbt/profiles.yml` local hợp lệ:

```powershell
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml build airflow-webserver ge-worker
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml up -d airflow-scheduler
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml ps
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T airflow-scheduler airflow dags list-import-errors
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T airflow-scheduler airflow dags unpause dbt_transform
$runId = 'tuan-quality-' + [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T airflow-scheduler airflow dags trigger dbt_transform --run-id $runId
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T airflow-scheduler airflow tasks states-for-dag-run dbt_transform $runId
```

Airflow UI: `http://localhost:8080`, tài khoản demo mặc định `admin`/`admin` nếu chưa được tùy chỉnh. Chờ cả năm task đạt `success`; `queued`/`running` chưa phải nghiệm thu hoàn tất. Không chạy dbt thủ công hoặc fixture verifier đồng thời với một lượt production DAG để tránh ghi chung project.

Linux: đặt `DOCKER_GID` bằng group của `/var/run/docker.sock` trước khi khởi động. Docker Desktop dùng group 0 theo overlay. Volume `airflow/logs` và `great_expectations/uncommitted` phải cho phép UID của Airflow ghi.

## Bằng chứng từng lần chạy

Host: `great_expectations/uncommitted/airflow/<run-hash>/<task-id>/try-<n>-<uuid>/`.

- `run-hash` là 20 ký tự đầu SHA-256 của `dag_id + "\n" + run_id`; UUID giúp lần retry/clear không ghi đè dữ liệu trước đó.
- Mỗi task có `task_summary.json` ghi native/final exit code, ngữ cảnh Airflow, timestamp và SHA-256 runner; `stdout.log` giữ chẩn đoán local.
- dbt run/test có `run_results.json` và `manifest.json`; docs có `catalog.json`, `manifest.json`, `index.html`. Không dùng artifact cũ từ lần chạy khác để xác nhận thành công.
- GE có `ge/summary.json` và kết quả hai checkpoints. Chỉ số tổng hợp được xuất, không xuất danh sách dòng customer sai.
- Airflow logs chỉ in đường dẫn bằng chứng và trạng thái tóm tắt. Nếu lỗi, xem log local tương ứng; không đẩy nguyên profile/credentials vào Git.

Hướng dẫn xem mô tả models, columns, tests và docs đã tạo: [dbt docs ngày 11–12](tuan_week3_dbt_docs.md).

## Kiểm chứng lỗi bằng fixtures

```powershell
$stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ')
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T airflow-scheduler python /opt/airflow/scripts/verify_airflow_quality.py --output-dir "/opt/airflow/quality_evidence/airflow-contracts-$stamp"
```

Verifier sử dụng chính hai operators GE/docs của DAG qua `DAG.test()` và schema fixture UUID do một tiến trình duy nhất tạo, quản lý, xóa và kiểm tra cleanup. Không sửa dữ liệu Silver thật. Các case:

| Case | GE native exit | Trạng thái GE | Trạng thái docs |
| --- | ---: | --- | --- |
| Dữ liệu hợp lệ, có NULL tùy chọn/miễn phí/discount 100% | 0 | success | success |
| Sai miền giá trị customer/order | 1 | failed | upstream_failed |
| Thiếu bảng order fixture | 2 | failed | upstream_failed |

Các DAG fixture đặt retries=0 để kiểm tra trạng thái cuối ngay. Một lần gọi lại helper với cùng context kiểm tra thư mục mới và toàn bộ bytes của bằng chứng cũ được giữ nguyên. Đây là kiểm chứng thực thi operators/dependencies trong `DAG.test()`, không thay cho bằng chứng scheduler chạy toàn bộ năm task trên dữ liệu thật.

## Nghiệm thu ngày 17/11/2026

Đã hoàn thành phạm vi Tuân ngày 11–12. Lượt `tuan-week3-day11-12-20261117-01` được trigger thủ công và thực thi bởi **scheduler/LocalExecutor**, từ 08:48:10 đến 08:53:21 giờ Việt Nam; cả năm tasks thành công ngay lần đầu.

| Hạng mục | Kết quả đã kiểm chứng |
| --- | --- |
| dbt run | 10/10 models thành công |
| dbt test | 200/200 PASS; giữ nguyên tập test IDs so với ngày 10 |
| GE trên Silver thật | 40/40 PASS; 19.820 customers và 121.317 order lines |
| dbt docs | Generate thành công; đủ mô tả 131 cột của 10 models, 59 trường thuộc 6 nguồn đang dùng |
| Fixtures qua `DAG.test()` | Hợp lệ: GE/docs success; dữ liệu sai (exit 1) và thiếu bảng (exit 2): GE failed, docs upstream_failed |
| Chạy lại helper cùng context | Tạo thư mục attempt mới, giữ nguyên toàn bộ bằng chứng trước đó |
| Cleanup fixtures | Đã xác nhận schema fixture được xóa; tiến trình quản lý exit 0 |

Bằng chứng và giới hạn chi tiết: [hồ sơ nghiệm thu](evidence/tuan-week3-day11-12/20261117/README.md), [trạng thái DAG thật](evidence/tuan-week3-day11-12/20261117/full_dag.json), [kết quả bốn bài thử](evidence/tuan-week3-day11-12/20261117/contracts/summary.json), [đối chiếu docs/catalog](evidence/tuan-week3-day11-12/20261117/docs_coverage.json).

Lượt nghiệm thu này không chạy lại freshness. `DQ-W2-01` của sáu nguồn lịch sử vẫn mở; kiểm thử scheduler retry, alert và cleanup tiến trình sau timeout vẫn thuộc phần phối hợp tiếp theo với Thịnh.

## Bàn giao

Thịnh rà soát lịch chạy, retries, notifications và monitoring chung. Bảo phụ trách CI/CD/deployment. Tuân tiếp tục ngày 13 đối chiếu Bronze → Silver → Gold và test coverage; ngày 14 hoàn thiện lineage/tài liệu; ngày 15 demo. Không dùng kết quả ngày 11–12 để tuyên bố toàn bộ hệ thống của nhóm đã nghiệm thu.
