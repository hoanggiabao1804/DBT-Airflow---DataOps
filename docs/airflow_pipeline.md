# Tầng orchestration và giám sát (Airflow)

Tài liệu này mô tả cách pipeline dữ liệu được điều phối bằng Apache Airflow, cách hệ thống xử lý
lỗi, ghi nhận và cảnh báo, cùng các kịch bản lỗi đã được kiểm thử. Phần này đáp ứng các yêu cầu
của mục _Airflow Orchestration_ trong đề bài: DAG chạy dbt đúng thứ tự, task dependencies,
lịch chạy, xử lý lỗi và retry, kiểm tra chất lượng dữ liệu trong pipeline và gửi thông báo khi
thất bại. Ngoài ra phần giám sát và health check hỗ trợ các mục _monitoring_, _runbook_ và
_post-deployment health checks_ của phần CI/CD.

## 1. Tổng quan

Hệ thống gồm bốn DAG:

| DAG                     | Lịch                           | Vai trò                                                                          |
| ----------------------- | ------------------------------ | -------------------------------------------------------------------------------- |
| `dbt_transform`         | 06:00 hằng ngày (giờ Việt Nam) | Pipeline chính: build Bronze → Silver → Gold, kiểm tra chất lượng, sinh tài liệu |
| `ge_data_quality`       | Phút 30, mỗi 6 giờ             | Kiểm tra lại chất lượng dữ liệu Silver giữa các lần build                        |
| `dataops_monitoring`    | Mỗi 30 phút                    | Giám sát sức khỏe toàn hệ thống và gửi cảnh báo khi trạng thái thay đổi          |
| `dataops_timeout_drill` | Chỉ chạy tay                   | Diễn tập tình huống task bị treo                                                 |

Airflow không cài dbt hay Great Expectations (GX) bên trong. Mỗi task gọi
`scripts/run_airflow_quality_task.py`, script này thực thi lệnh trong container `dbt` hoặc
`ge-worker` bằng `docker exec`. Nhờ vậy môi trường của từng công cụ được tách biệt, còn Airflow
chỉ đảm nhận việc điều phối. Định nghĩa test nằm ở `dbt/models/*/schema.yml` và `dbt/tests/`,
expectation GX ở `great_expectations/expectations/`.

## 2. DAG `dbt_transform`

```text
check_runtime → dbt_deps → dbt_run → dbt_test → ge_validate → dbt_docs
```

| Task            | Chức năng                                                                                |            Số lần retry | Timeout |
| --------------- | ---------------------------------------------------------------------------------------- | ----------------------: | ------: |
| `check_runtime` | Xác nhận container `dbt` và `ge-worker` đang chạy, `dbt debug` đăng nhập được SQL Server |                       2 |  3 phút |
| `dbt_deps`      | Cài package dbt (`dbt_utils`), cần kết nối mạng                                          |                       3 | 10 phút |
| `dbt_run`       | Build 10 model Bronze → Silver → Gold                                                    |                       2 | 30 phút |
| `dbt_test`      | Chạy toàn bộ 202 schema/generic/singular test                                            |                       2 | 20 phút |
| `ge_validate`   | Chạy 2 checkpoint GX (customer, order) với 40 expectation trên Silver                    | 1, chỉ cho lỗi thực thi | 20 phút |
| `dbt_docs`      | Sinh tài liệu dbt                                                                        |                       1 | 10 phút |

Mọi phụ thuộc giữa các task đều là `all_success`: một task thất bại thì toàn bộ task phía sau
chuyển sang `upstream_failed`. Vì vậy `dbt_test` và `ge_validate` đóng vai trò **cổng chặn chất
lượng**: dữ liệu không đạt kiểm tra thì tài liệu không được sinh ra.

Task `check_runtime` (`scripts/check_runtime.sh`) được thêm vào đầu pipeline để **phát hiện lỗi
hạ tầng sớm**. Nếu không có task này, khi container hoặc SQL Server ngừng hoạt động, lỗi chỉ lộ ra
ở các bước sau dưới dạng lỗi Docker/ODBC khó đọc. Với `check_runtime`, pipeline dừng ngay sau vài
giây kèm thông báo rõ ràng, ví dụ:

```text
Service ge-worker: expected 1 running container, found 0
dbt debug: FAILED or >30 s (target dev) - SQL Server down or profile invalid
```

Thời gian chạy toàn bộ DAG khi bình thường khoảng 45 giây.

## 3. Lịch chạy

- Lịch mặc định `0 6 * * *` với timezone `Asia/Ho_Chi_Minh`, tức 06:00 giờ Việt Nam (23:00 UTC
  ngày hôm trước). Airflow lưu và hiển thị thời gian theo UTC.
- `catchup=False`: AdventureWorks là dữ liệu lịch sử cố định nên hệ thống không chạy bù các ngày
  đã lỡ, chỉ chạy khoảng thời gian gần nhất.
- `max_active_runs=1`: tại mỗi thời điểm chỉ có một lần chạy, tránh hai tiến trình cùng ghi vào
  một bảng.
- `is_paused_upon_creation=True`: DAG mới triển khai ở trạng thái tạm dừng cho đến khi được bật,
  để không tự chạy trước khi được kiểm tra.
- Lịch được cấu hình qua biến môi trường `DATAOPS_SCHEDULE` (giá trị `manual` để chỉ chạy tay),
  không cần sửa code khi đổi môi trường.

## 4. Xử lý lỗi

Hệ thống phân biệt hai loại lỗi và xử lý khác nhau.

**Lỗi tạm thời** (mất kết nối mạng, SQL Server khởi động lại, Docker bận) có thể tự hết sau một
thời gian. Các task được retry với **exponential backoff**: khoảng chờ tăng dần 1 → 2 → 4 phút,
tối đa 10 phút. Hệ thống có thời gian hồi phục mà không bị gọi liên tục khi đang quá tải. Số lần
retry khác nhau theo task: `dbt_deps` phụ thuộc mạng nên được retry nhiều nhất.

**Lỗi dữ liệu** (expectation GX không đạt) cho cùng một kết quả dù chạy lại bao nhiêu lần.
`ge_validate` dùng `QualityStepOperator` (`airflow/dags/utils/operators.py`): khi GX trả exit
code 1, task thất bại ngay mà không retry. Kết quả đo được: thời gian một lần chạy có dữ liệu sai
giảm từ khoảng 2 phút 10 giây xuống 16 giây, và chỉ có một cảnh báo thay vì nhiều cảnh báo lặp.
Các bước dbt vẫn được retry vì dbt trả cùng exit code 1 cho cả lỗi SQL và lỗi mất kết nối, nên
không thể phân biệt hai trường hợp.

**Timeout** có hai mức:

- `execution_timeout` theo từng task, đặt lớn hơn nhiều lần thời gian thực tế. Khi timeout xảy ra
  thì task thực sự bị treo, không phải chỉ chạy chậm.
- `dagrun_timeout=2h` cho cả lần chạy. Do chỉ cho phép một lần chạy tại một thời điểm, giới hạn
  này đảm bảo một lần chạy bị treo không chặn các lần chạy theo lịch sau đó.

**Dọn tiến trình khi task bị hủy.** Khi Airflow hủy một task (timeout, clear, mark failed), tín
hiệu SIGTERM chỉ tới tiến trình runner trong container Airflow. Tiến trình dbt/GX thật sự chạy
trong container khác và có thể tiếp tục chạy ngầm, gây xung đột với lần retry sau. Runner gắn một
mã định danh riêng cho mỗi lần chạy vào tiến trình trong container. Khi nhận SIGTERM, runner tìm
và dừng đúng các tiến trình mang mã đó, rồi ghi `status: killed` vào `task_summary.json`.

## 5. Logging và metrics

Mọi task được gắn callback (`airflow/dags/utils/callbacks.py`), Airflow tự gọi các callback này
khi task bắt đầu, thành công, retry hoặc thất bại và khi DAG kết thúc. Mỗi sự kiện tạo ra hai đầu
ra:

- Một dòng log có cấu trúc `DATAOPS_EVENT {...}` dạng JSON trong log của task, đọc được trên
  Airflow UI.
- Một bản ghi trong `airflow/logs/dataops_metrics/task_metrics.jsonl`, gồm thời gian chạy, lần
  thử, trạng thái. Monitoring DAG và health check đọc file này để tính tỉ lệ thành công và thời
  gian chạy.

Các nguyên tắc thiết kế:

- Code giám sát không bao giờ làm thay đổi kết quả pipeline. Mọi callback được bọc để nếu có lỗi
  (ví dụ đĩa đầy) thì chỉ ghi cảnh báo, không đánh dấu một task thành công thành thất bại.
- Các bản ghi được ghi nối tiếp bằng một thao tác ghi đơn, nên nhiều task ghi đồng thời không bị
  trộn dòng.
- Tỉ lệ thành công được tính bằng `task_success / (task_success + task_failure)`. Lần retry là
  bước trung gian nên không tính vào mẫu số.
- Hai lỗi của Airflow 2.7 đã được xử lý và có unit test: `try_number` trong callback bị lệch một
  đơn vị, và DAG callback nhận thông tin của task cuối cùng thay vì của cả DAG.

Phần logging, alerting và monitoring có 28 unit test (`airflow/tests/`), chạy được mà không cần
Airflow nhờ dùng đối tượng giả lập thay cho context của Airflow.

## 6. Cảnh báo (alert)

`airflow/dags/utils/alerting.py` gửi cảnh báo tới ba kênh:

| Kênh              | Điều kiện                                      | Ghi chú                                                                    |
| ----------------- | ---------------------------------------------- | -------------------------------------------------------------------------- |
| File log cảnh báo | Luôn bật                                       | `airflow/logs/dataops_alerts/alerts.jsonl`, hoạt động cả khi không có mạng |
| Webhook           | Có biến `DATAOPS_ALERT_WEBHOOK_URL`            | Hỗ trợ định dạng Slack, Discord, Teams                                     |
| Email             | Có biến `DATAOPS_ALERT_EMAIL` và cấu hình SMTP | Dùng cơ chế email của Airflow                                              |

Các sự kiện tạo cảnh báo:

| Sự kiện                                                                | Mức độ                                        |
| ---------------------------------------------------------------------- | --------------------------------------------- |
| Task thất bại nhưng còn lượt retry                                     | warning                                       |
| Task thất bại hẳn                                                      | critical                                      |
| DAG thất bại vì lý do khác task thất bại, ví dụ vượt `dagrun_timeout`  | critical                                      |
| `dbt_docs` hoàn thành trễ hơn 1 giờ so với lịch (SLA)                  | warning                                       |
| Sức khỏe hệ thống chuyển sang xấu / sự cố kéo dài quá 6 giờ / phục hồi | critical / warning / info                     |
| Kiểm tra GX thất bại                                                   | critical, kèm số expectation đạt và không đạt |

Mỗi cảnh báo ghi rõ mức độ, DAG, task, lần chạy, lần thử, đường dẫn log và đường dẫn runbook.
Việc gửi cảnh báo thất bại không ảnh hưởng đến trạng thái pipeline. URL webhook được xem là bí mật:
chỉ đọc từ biến môi trường, không ghi vào log hay nội dung cảnh báo. Khi trình diễn không có Slack,
nhóm dùng `scripts/alert_webhook_receiver.py`, một web server nhỏ đóng vai Slack để nhận và ghi
lại cảnh báo.

## 7. Monitoring DAG `dataops_monitoring`

```text
check_services ─┐
check_pipeline ─┤
check_metrics  ─┼─> publish_report
check_disk     ─┘
```

| Kiểm tra | Critical khi                                                                                           | Warning khi                                                      |
| -------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------- |
| services | Một trong 6 service không chạy hoặc `unhealthy`                                                        | —                                                                |
| pipeline | Lần chạy `dbt_transform` gần nhất thất bại, hoặc DAG đang có lịch mà lần thành công cuối đã quá 26 giờ | DAG tạm dừng và lần thành công cuối quá cũ                       |
| metrics  | —                                                                                                      | Tỉ lệ task thành công của `dbt_transform` trong 24 giờ dưới 80 % |
| disk     | Dưới 2 GB trống                                                                                        | Dưới 5 GB trống                                                  |

Callback chỉ hoạt động khi có task chạy. Nếu scheduler hoặc một service ngừng hoạt động thì sẽ
không có lần chạy nào và cũng không có callback nào được gọi. Monitoring DAG chủ động kiểm tra định
kỳ để phát hiện cả những trường hợp này, và báo khi hệ thống phục hồi.

Để tránh gửi cảnh báo lặp lại, monitoring lưu trạng thái lần kiểm tra trước
(`airflow/logs/dataops_monitoring/latest.json`) và chỉ gửi cảnh báo khi trạng thái **thay đổi**:
từ bình thường sang lỗi, hoặc từ lỗi sang bình thường (cảnh báo `recovered`). Nếu sự cố kéo dài,
cảnh báo được nhắc lại sau mỗi 6 giờ. Các ngưỡng được cấu hình qua biến môi trường.

## 8. DAG chất lượng dữ liệu `ge_data_quality`

```text
wait_for_transform_idle → check_runtime → ge_validate → publish_quality_report
```

`dbt_transform` kiểm tra dữ liệu ngay sau khi build. DAG này trả lời một câu hỏi khác: dữ liệu ở
thời điểm hiện tại có còn hợp lệ không.

- `wait_for_transform_idle` chờ cho đến khi `dbt_transform` không còn chạy, tránh kiểm tra đúng
  lúc bảng Silver đang được ghi lại và báo lỗi sai.
- `publish_quality_report` chạy bất kể `ge_validate` thành công hay thất bại
  (`trigger_rule="all_done"`). Task này ghi metric cho từng checkpoint, gửi một cảnh báo chi tiết
  khi có lỗi, rồi đánh dấu lần chạy thất bại để trạng thái trên UI phản ánh đúng chất lượng dữ liệu.
- Tham số `schema` cho phép kiểm tra một schema khác `silver`. Tham số này được dùng cho diễn tập
  với schema `dq_drill`, một bản sao Silver có cấy lỗi (`scripts/dq_drill.sh`), để dữ liệu thật
  không bị ảnh hưởng.

## 9. Health check và xử lý sự cố

`scripts/health_check.py` kiểm tra toàn bộ hệ thống bằng một lệnh và trả exit code
0 (bình thường), 1 (cảnh báo), 2 (nghiêm trọng). Nhờ đó cả người vận hành lẫn script tự động
(cron, CI, bước kiểm tra sau deploy) đều dùng được kết quả.

| Kiểm tra    | Nội dung                                                       | Mức khi lỗi                    |
| ----------- | -------------------------------------------------------------- | ------------------------------ |
| docker      | Docker daemon truy cập được                                    | FAIL                           |
| services    | 6 service Compose đang chạy, không `unhealthy`                 | FAIL                           |
| sqlserver   | Database `AdventureWorks2014` ở trạng thái `ONLINE`            | FAIL                           |
| dbt         | `dbt debug` trong container dbt thành công                     | FAIL                           |
| airflow     | Metadata DB và heartbeat của scheduler                         | FAIL                           |
| dag_imports | Không có DAG lỗi import                                        | FAIL                           |
| last_run    | Lần chạy `dbt_transform` gần nhất không thất bại               | FAIL                           |
| orphans     | Không có tiến trình dbt/GX chạy ngầm khi không có lần chạy nào | WARN                           |
| monitoring  | Kết quả monitoring còn mới (dưới 1 giờ) và trạng thái của nó   | theo monitoring                |
| alerts_24h  | Không còn cảnh báo critical chưa được đóng                     | WARN                           |
| disk        | Dung lượng trống của ổ đĩa                                     | WARN dưới 5 GB, FAIL dưới 2 GB |

Mỗi kiểm tra lỗi đi kèm gợi ý cách xử lý. Quy trình xử lý chi tiết cho từng loại sự cố nằm trong
[incident_runbook.md](incident_runbook.md). Sau mỗi sự cố, nhóm ghi báo cáo theo
[incident_template.md](incident_template.md); một báo cáo mẫu từ diễn tập mất SQL Server nằm trong
[incidents/](incidents/).

## 10. Kiểm thử các kịch bản lỗi

Các kịch bản dưới đây được tạo ra có chủ đích trên môi trường thật để kiểm chứng toàn bộ chuỗi
phát hiện, cảnh báo và phục hồi.

| #   | Kịch bản                     | Phát hiện bởi                             | Retry         | Cảnh báo                          | Phục hồi                                            |
| --- | ---------------------------- | ----------------------------------------- | ------------- | --------------------------------- | --------------------------------------------------- |
| 1   | Container `ge-worker` dừng   | `check_runtime`, monitoring, health check | Có, backoff   | warning, critical                 | Khởi động lại container, chạy lại task              |
| 2   | SQL Server dừng              | `check_runtime`, monitoring, health check | Có, backoff   | warning, critical, recovered      | Retry tự chạy tiếp sau khi SQL Server hoạt động lại |
| 3   | Dữ liệu sai                  | `ge_validate`                             | Không         | Một cảnh báo critical có chi tiết | Sửa dữ liệu hoặc model                              |
| 4   | Task bị treo, vượt timeout   | Airflow `execution_timeout`               | Theo cấu hình | critical                          | Runner tự dừng tiến trình trong container           |
| 5   | Tiến trình dbt chạy ngầm     | Health check (`orphans`)                  | —             | WARN                              | Theo runbook mục 2.5                                |
| 6   | Hệ thống trở lại bình thường | monitoring                                | —             | info `recovered`                  | —                                                   |

Kết quả đo được trong lần kiểm thử cuối:

| Kịch bản                                                   | Kết quả                                                                                                                                                                    |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Chạy bình thường                                           | `dbt_transform` 6/6 task thành công trong 45 giây; ghi đủ 7 bản ghi metrics                                                                                                |
| Dữ liệu sai (25 + 40 + 15 dòng lỗi cấy vào bản sao Silver) | `ge_validate` thất bại ngay lần đầu, không retry; cảnh báo báo đúng customer 9/10, order 28/30 expectation đạt                                                             |
| SQL Server dừng giữa lúc chạy                              | Health check báo CRITICAL ngay; cảnh báo đầu tiên sau 43 giây; sau khi SQL Server hoạt động lại, pipeline tự hoàn thành 6/6 nhờ retry; monitoring gửi cảnh báo `recovered` |
| Task bị treo                                               | Task bị dừng sau 5 giây, runner dừng 2 tiến trình trong container, health check xác nhận không còn tiến trình chạy ngầm                                                    |

Các bước tái hiện từng kịch bản khi trình diễn nằm trong [demo_guide.md](demo_guide.md), phần 4
và 5.

## 11. Cấu hình

Toàn bộ cấu hình đọc từ biến môi trường của container Airflow, nên cùng một mã nguồn chạy được trên
nhiều môi trường mà không cần sửa code.

| Biến                           | Mặc định       | Ý nghĩa                                        |
| ------------------------------ | -------------- | ---------------------------------------------- |
| `DATAOPS_SCHEDULE`             | `0 6 * * *`    | Lịch `dbt_transform`; `manual` để chỉ chạy tay |
| `DATAOPS_GE_SCHEDULE`          | `30 */6 * * *` | Lịch `ge_data_quality`                         |
| `DATAOPS_MONITORING_SCHEDULE`  | `*/30 * * * *` | Lịch `dataops_monitoring`                      |
| `DATAOPS_DBT_TARGET`           | `dev`          | Target dbt trong `dbt/profiles.yml`            |
| `DATAOPS_GE_SCHEMA`            | `silver`       | Schema được GX kiểm tra                        |
| `DATAOPS_ALERT_WEBHOOK_URL`    | (trống)        | Địa chỉ webhook Slack/Discord/Teams            |
| `DATAOPS_ALERT_WEBHOOK_FORMAT` | `generic`      | Định dạng tin nhắn webhook                     |
| `DATAOPS_ALERT_EMAIL`          | (trống)        | Địa chỉ nhận cảnh báo qua email                |
| `DATAOPS_ALERT_ON_RETRY`       | `true`         | Gửi cảnh báo warning khi task retry            |
