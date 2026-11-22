# Kịch bản demo

Buổi demo trình bày **một quy trình DataOps liền mạch** thay vì từng thành phần riêng lẻ: một thay
đổi mã nguồn đi từ pull request qua CI, được triển khai tự động, pipeline xử lý dữ liệu, hệ thống
giám sát ghi nhận kết quả, và cuối cùng là tình huống sự cố được phát hiện, xử lý và khôi phục.
Tổng thời lượng khoảng 20–25 phút.

| # | Nội dung | Yêu cầu đề bài được chứng minh | Người trình bày | Thời gian |
| --- | --- | --- | --- | --- |
| 1 | Mở pull request, CI tự động chạy lint và test | CI workflow, automated testing on PR | Bảo | 4 phút |
| 2 | CI đạt, merge vào `develop`, triển khai tự động | Automated deployment, environment-specific deployment | Bảo | 3 phút |
| 3 | dbt build Bronze → Silver → Gold, test, kiểm tra GX, smoke test | DBT models, automated testing, data quality | Tuân | 5 phút |
| 4 | Airflow và giám sát: DAG, log, metrics, cảnh báo khi dữ liệu sai | Airflow orchestration, notifications on failure | Thịnh | 5 phút |
| 5 | Sự cố hạ tầng: phát hiện, cảnh báo, khôi phục, rollback | Error handling, health checks, runbook, rollback | Thịnh, Bảo | 5 phút |
| — | Hỏi đáp | | Cả nhóm | |

## Môi trường demo

Trước buổi demo, hệ thống được khởi động và kiểm tra bằng `scripts/health_check.py` (kết quả phải
là `OVERALL: OK`). Hai DAG `dbt_transform` và `ge_data_quality` được bật, và một lần chạy
`dbt_transform` thành công được thực hiện trước để monitoring ở trạng thái bình thường.

Cảnh báo được gửi tới Slack/Discord nếu có cấu hình webhook thật. Nếu không, nhóm dùng
`scripts/alert_webhook_receiver.py`, một web server nhỏ đóng vai Slack, nhận cảnh báo và ghi lại
từng tin nhắn để hiển thị trên màn hình. Trong lúc demo, ba màn hình được mở sẵn: Airflow UI,
GitHub Actions và màn hình nhận cảnh báo.

## Phần 4 — Airflow và giám sát

Phần này cho thấy pipeline được điều phối như thế nào và hệ thống phản ứng ra sao khi dữ liệu sai.

| Bước | Diễn biến | Điểm được chứng minh |
| --- | --- | --- |
| 4.1 | Trang DAGs của Airflow hiển thị `dbt_transform`, `ge_data_quality`, `dataops_monitoring` | Ba DAG với ba lịch chạy: 06:00 hằng ngày, mỗi 6 giờ, mỗi 30 phút |
| 4.2 | Sơ đồ Graph của `dbt_transform` | Thứ tự task; `check_runtime` phát hiện lỗi hạ tầng sớm; GX là cổng chặn trước bước sinh tài liệu |
| 4.3 | Log của task `dbt_test` trong lần chạy gần nhất | Dòng tóm tắt `202 pass` kèm đường dẫn bằng chứng, và các dòng log có cấu trúc `DATAOPS_EVENT` |
| 4.4 | File metrics `task_metrics.jsonl` | Mỗi task được ghi lại thời gian chạy và số lần thử |
| 4.5 | Nhóm tạo bản sao Silver có cấy 3 loại lỗi (25 + 40 + 15 dòng) bằng `scripts/dq_drill.sh`, rồi chạy `ge_data_quality` trên bản sao này | Dữ liệu Silver thật không bị ảnh hưởng |
| 4.6 | Khoảng 20 giây sau, cảnh báo `Data quality FAILED on dq_drill … customer_checkpoint: 9/10 … order_checkpoint: 28/30` xuất hiện | Cảnh báo chỉ ra đúng 3 lỗi đã cấy; `ge_validate` thất bại ngay lần đầu, không retry vì lỗi dữ liệu không tự hết |
| 4.7 | Bản sao có lỗi được xóa | Môi trường trở lại như trước |

## Phần 5 — Sự cố hạ tầng và khôi phục

Phần này mô phỏng một sự cố thật: SQL Server ngừng hoạt động trong lúc pipeline đang chạy.

| Bước | Diễn biến | Kết quả |
| --- | --- | --- |
| 5.1 | SQL Server bị dừng, đồng thời `dbt_transform` được kích hoạt | — |
| 5.2 | Chạy health check | Báo `[FAIL] services sqlserver exited` và `[FAIL] sqlserver container not running`, kèm gợi ý cách xử lý; exit code 2 |
| 5.3 | Pipeline gặp lỗi ở `check_runtime` | Sau khoảng 40 giây có cảnh báo `Task retry: dbt_transform.check_runtime`; monitoring gửi `DataOps health CRITICAL: services` |
| 5.4 | Người trực tra [incident_runbook.md](incident_runbook.md), bảng tra cảnh báo dẫn tới mục 2.1 | Quy trình xử lý có sẵn, không phải ứng biến |
| 5.5 | SQL Server được khởi động lại | Lần retry kế tiếp của `check_runtime` thành công, pipeline tự chạy tiếp đến hết 6/6 task. Nếu đã hết lượt retry, task được chạy lại bằng thao tác Clear trên Airflow UI |
| 5.6 | Monitoring chạy lại | Cảnh báo `DataOps recovered: all checks OK`; health check trở về `OVERALL: OK` |
| 5.7 | Trình bày [báo cáo sự cố mẫu](incidents/20261119-sqlserver-outage-drill.md) từ lần diễn tập trước | Báo cáo blameless gồm thời gian phát hiện, phân tích 5 Whys và hành động phòng ngừa |
| 5.8 | Bảo trình bày rollback bằng `scripts/rollback.sh` | Release dbt trước đó được khôi phục và kiểm tra lại bằng smoke test |

Nếu thời gian chờ retry quá lâu so với thời lượng demo, nhóm dừng container `ge-worker` thay cho
SQL Server. Khi đó `check_runtime` thất bại ngay trong mỗi lần thử, nên chuỗi cảnh báo xuất hiện
nhanh hơn.

## Các câu hỏi về thiết kế

| Câu hỏi | Giải thích |
| --- | --- |
| Vì sao cần cả callback và monitoring DAG? | Callback chỉ chạy khi có task chạy. Monitoring kiểm tra định kỳ nên phát hiện được cả khi không có lần chạy nào (scheduler hoặc service ngừng hoạt động), và báo khi hệ thống phục hồi |
| Làm sao tránh gửi cảnh báo lặp lại? | Monitoring chỉ cảnh báo khi trạng thái thay đổi và nhắc lại sau 6 giờ nếu sự cố kéo dài. DAG thất bại do task thất bại không tạo cảnh báo thứ hai. Kiểm tra GX thất bại chỉ tạo một cảnh báo |
| Khi task bị timeout, tiến trình dbt trong container có chạy tiếp không? | Không. Runner gắn mã định danh cho tiến trình trong container và dừng đúng các tiến trình đó khi task bị hủy. DAG `dataops_timeout_drill` dùng để kiểm chứng điều này |
| URL webhook có bị lộ không? | Không. URL chỉ được đọc từ biến môi trường (file `.env` không được commit), không xuất hiện trong log hay nội dung cảnh báo |
| Vì sao lỗi GX không retry còn lỗi dbt thì có? | GX trả exit code 1 chỉ khi dữ liệu sai, chạy lại vẫn cho cùng kết quả. dbt trả exit code 1 cả khi mất kết nối database, trường hợp này có thể tự hết nên vẫn được retry |
| Kết quả có kiểm chứng được không? | Toàn bộ kịch bản chạy lại được bằng các lệnh ở phụ lục; kết quả đo được của từng kịch bản lỗi nằm trong [airflow_pipeline.md](airflow_pipeline.md#10-kiểm-thử-các-kịch-bản-lỗi) |

## Phụ lục: lệnh sử dụng trong demo

Chuẩn bị môi trường:

```bash
cd DBT-Airflow---DataOps
export COMPOSE_PROJECT_NAME=dbt_airflow_project
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) AIRFLOW_UID=$(id -u)
DC="docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml"
AF="$DC exec -T airflow-scheduler airflow"

# Receiver giả lập Slack (bỏ qua nếu dùng webhook thật trong .env)
docker run -d --name alert-receiver --network ${COMPOSE_PROJECT_NAME}_dbt_airflow_network \
  --network-alias alert-receiver --user "$(id -u):0" --entrypoint python \
  -v "$PWD/scripts:/s:ro" -v "$PWD/airflow/logs:/out" \
  ${COMPOSE_PROJECT_NAME}-airflow-quality:2.7.1 /s/alert_webhook_receiver.py --output /out/webhook_received.jsonl
export DATAOPS_ALERT_WEBHOOK_URL=http://alert-receiver:9099/alert DATAOPS_ALERT_WEBHOOK_FORMAT=slack

$DC up -d --wait airflow-scheduler
python3 scripts/health_check.py
$AF dags unpause dbt_transform; $AF dags unpause ge_data_quality
$AF dags trigger dbt_transform --run-id demo-warmup-$(date +%H%M)
tail -f airflow/logs/webhook_received.jsonl          # màn hình nhận cảnh báo
```

Phần 4:

```bash
tail -3 airflow/logs/dataops_metrics/task_metrics.jsonl                      # 4.4
./scripts/dq_drill.sh setup                                                  # 4.5
$AF dags trigger ge_data_quality --conf '{"schema":"dq_drill"}'              # 4.5
./scripts/dq_drill.sh teardown                                               # 4.7
```

Phần 5:

```bash
$DC stop sqlserver                                                           # 5.1
$AF dags trigger dbt_transform --run-id demo-outage                          # 5.1
python3 scripts/health_check.py --skip-dbt                                   # 5.2
$DC start sqlserver                                                          # 5.5
$AF dags trigger dataops_monitoring                                          # 5.6
python3 scripts/health_check.py                                              # 5.6
./scripts/rollback.sh dev backups/dev_<timestamp>_<id> --yes                 # 5.8
```

Sau demo:

```bash
docker rm -f alert-receiver
python3 scripts/health_check.py --resolve "demo finished"
```
