# DBT + Airflow + SQL Server — DataOps Project

Đồ án xây dựng một pipeline dữ liệu hoàn chỉnh trên bộ dữ liệu AdventureWorks2014 theo mô hình
**Bronze → Silver → Gold**. Dữ liệu được biến đổi bằng dbt, điều phối bằng Apache Airflow và vận
hành theo các nguyên tắc DataOps: quản lý mã nguồn bằng Git, CI/CD với GitHub Actions, kiểm thử tự
động, kiểm tra chất lượng dữ liệu bằng Great Expectations, giám sát, cảnh báo và quy trình xử lý sự
cố.

Danh mục tài liệu nộp bài (sơ đồ kiến trúc PDF/PNG, hướng dẫn cài đặt, tài liệu model,
troubleshooting) nằm trong [docs/README.md](docs/README.md). Hướng dẫn lab gốc của môn học được
giữ nguyên ở [`1. README.md`](1.%20README.md) và [`0. NEW_COMPUTER_SETUP.md`](0.%20NEW_COMPUTER_SETUP.md).

## 1. Đối chiếu với yêu cầu đề bài

| Hạng mục | Nội dung thực hiện | Vị trí |
| --- | --- | --- |
| DBT Data Models | 10 model chia ba lớp Bronze, Silver, Gold | `dbt/models/` |
| Automated Testing | 202 test: schema test, generic test, singular test và kiểm tra source freshness | `dbt/models/*/schema.yml`, `dbt/tests/`, `dbt/models/bronze/src_adventureworks.yml` |
| Airflow Orchestration | DAG chạy dbt đúng thứ tự, có lịch, retry, kiểm tra chất lượng trong pipeline và cảnh báo khi thất bại | `airflow/dags/`, [docs/airflow_pipeline.md](docs/airflow_pipeline.md) |
| CI/CD & Deployment | CI trên mọi pull request; triển khai tự động khi merge vào `develop`/`main`; smoke test, release và rollback | `.github/workflows/`, `scripts/deploy.sh`, `scripts/rollback.sh` |
| Monitoring & Incident Response | Monitoring DAG, health check, runbook và báo cáo sự cố | [docs/airflow_pipeline.md](docs/airflow_pipeline.md), [docs/incident_runbook.md](docs/incident_runbook.md) |
| Documentation | README, sơ đồ kiến trúc, kịch bản demo | [docs/architecture.md](docs/architecture.md), [docs/demo_guide.md](docs/demo_guide.md) |

## 2. Kiến trúc

```mermaid
flowchart LR
    gh[GitHub PR] -->|CI| ci[GitHub Actions<br/>lint · dbt test]
    gh -->|merge develop| cd[Deploy<br/>smoke · release]
    subgraph compose[Docker Compose]
        af[Airflow] -->|docker exec| dbt[dbt] & ge[Great Expectations]
        dbt & ge --> mssql[(SQL Server<br/>bronze/silver/gold)]
    end
    af -->|alert| chat[[Slack/Discord]]
    ops([On-call]) -->|health_check · runbook| compose
```

Toàn bộ hệ thống chạy trên Docker Compose. Airflow không cài dbt hay Great Expectations bên trong
mà gọi sang container riêng của từng công cụ, nhờ vậy môi trường của các công cụ được tách biệt và
Airflow chỉ đảm nhận việc điều phối. Sơ đồ chi tiết và các quyết định thiết kế nằm trong
[docs/architecture.md](docs/architecture.md).

| Thành phần | Phiên bản | Vai trò |
| --- | --- | --- |
| SQL Server | 2019 Express | Chứa dữ liệu nguồn AdventureWorks2014 và các schema bronze/silver/gold |
| dbt | 1.8.7 (dbt-sqlserver) | Biến đổi dữ liệu qua 10 model và chạy 202 test |
| Great Expectations | 0.18.22 | Kiểm tra chất lượng dữ liệu Silver với 2 bộ, tổng 40 expectation |
| Airflow | 2.7.1, LocalExecutor, Postgres 13 | Điều phối pipeline: 3 DAG vận hành và 1 DAG diễn tập |

## 3. Luồng dữ liệu

| Lớp | Dạng lưu trữ | Nội dung |
| --- | --- | --- |
| Bronze | View | Dữ liệu thô từ AdventureWorks2014 (khách hàng, sản phẩm, đơn hàng), chưa biến đổi |
| Silver | Table | Dữ liệu đã làm sạch và chuẩn hóa: 19.820 khách hàng, 504 sản phẩm, 121.317 dòng đơn hàng |
| Gold | Table | Bảng tổng hợp phục vụ phân tích: chỉ số khách hàng, hiệu quả sản phẩm, tổng hợp doanh số |

Sau mỗi lần build, dữ liệu phải vượt qua 202 dbt test và 40 expectation của Great Expectations.
Nếu bất kỳ kiểm tra nào không đạt, pipeline dừng lại và gửi cảnh báo.

## 4. Điều phối và giám sát

| DAG | Lịch | Luồng xử lý |
| --- | --- | --- |
| `dbt_transform` | 06:00 hằng ngày (giờ Việt Nam) | `check_runtime → dbt_deps → dbt_run → dbt_test → ge_validate → dbt_docs` |
| `ge_data_quality` | Phút 30, mỗi 6 giờ | `wait_for_transform_idle → check_runtime → ge_validate → publish_quality_report` |
| `dataops_monitoring` | Mỗi 30 phút | Kiểm tra services, pipeline, metrics, disk → `publish_report` |
| `dataops_timeout_drill` | Chỉ chạy tay | Diễn tập tình huống task bị treo |

Pipeline phân biệt lỗi tạm thời (được retry với thời gian chờ tăng dần) và lỗi dữ liệu (dừng ngay,
không retry). Mọi sự kiện của task được ghi thành log có cấu trúc và metrics. Cảnh báo được gửi qua
webhook (Slack, Discord, Teams) hoặc email. Monitoring DAG chủ động kiểm tra sức khỏe hệ thống,
chỉ gửi cảnh báo khi trạng thái thay đổi và báo khi hệ thống phục hồi. Thiết kế chi tiết và kết quả
kiểm thử các kịch bản lỗi nằm trong [docs/airflow_pipeline.md](docs/airflow_pipeline.md).

## 5. Quy trình phát triển và CI/CD

```text
main ← develop ← feature/<tên-thành-viên>-<tuần>-<ngày>
```

- Mỗi thành viên làm việc trên nhánh `feature/*` tách từ `develop`. Mọi thay đổi vào `develop`
  đi qua pull request, có ít nhất một thành viên khác review, và tiêu đề theo Conventional Commits
  (`feat:`, `fix:`, `docs:` …).
- CI chạy tự động trên mọi pull request và là điều kiện bắt buộc để merge:
  `python-quality` (black, flake8, pylint), `dbt-ci` (sqlfluff, dbt run/test trên SQL Server tạm)
  và `pr-checks` (định dạng tiêu đề, kích thước, xung đột).
- Khi merge vào `develop`, workflow deploy dựng một SQL Server staging tạm, chạy dbt, smoke test và
  tạo release artifact. Merge vào `main` triển khai lên môi trường production.
- Pre-commit hook (`.pre-commit-config.yaml`) kiểm tra định dạng mã nguồn trước mỗi commit.
- Phần logging, alerting và monitoring có 28 unit test (`airflow/tests/`) chạy được mà không cần
  Airflow.

## 6. Vận hành và xử lý sự cố

| Chức năng | Cách thực hiện |
| --- | --- |
| Kiểm tra sức khỏe | `scripts/health_check.py` kiểm tra 11 hạng mục bằng một lệnh, trả exit code 0/1/2 để dùng được trong script và CI |
| Cảnh báo | Gửi qua webhook hoặc email theo cấu hình; mọi cảnh báo đều được ghi lại trong `airflow/logs/dataops_alerts/alerts.jsonl` |
| Xử lý sự cố | Quy trình cho từng loại sự cố trong [docs/incident_runbook.md](docs/incident_runbook.md) |
| Báo cáo sự cố | Mẫu báo cáo blameless [docs/incident_template.md](docs/incident_template.md) và một báo cáo mẫu trong [docs/incidents/](docs/incidents/) |
| Deploy và rollback | `scripts/deploy.sh` triển khai và tạo release đã kiểm chứng; `scripts/rollback.sh` khôi phục release trước đó |
| Diễn tập lỗi dữ liệu | `scripts/dq_drill.sh` tạo bản sao Silver có cấy lỗi để kiểm thử cảnh báo mà không ảnh hưởng dữ liệu thật |

## 7. Cài đặt và chạy

Hệ thống được khởi động bằng các lệnh sau (Linux):

```bash
export COMPOSE_PROJECT_NAME=dbt_airflow_project
export DOCKER_GID=$(stat -c '%g' /var/run/docker.sock) AIRFLOW_UID=$(id -u)
DC="docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml"

$DC build
$DC up -d sqlserver dbt
$DC exec -T sqlserver /tmp/restore_db.sh                  # lần đầu: restore AdventureWorks2014
# lần đầu: tạo login dbt theo "0. NEW_COMPUTER_SETUP.md" bước 2
$DC up -d --wait airflow-scheduler                        # init, webserver, ge-worker, scheduler
python3 scripts/health_check.py                           # kết quả mong đợi: OVERALL: OK
```

Airflow UI chạy tại <http://localhost:8080> (tài khoản `admin` / `admin`, chỉ dùng cho môi trường
lab). Các biến cấu hình như lịch chạy, webhook cảnh báo và email được liệt kê trong
[`.env.example`](.env.example).

## 8. Phân công

| Thành viên | Vai trò | Phạm vi | Mã nguồn và tài liệu chính |
| --- | --- | --- | --- |
| Bảo | Technical Lead / DevOps | Git, CI/CD, Deployment | `.github/workflows/`, `scripts/deploy.sh`, `scripts/rollback.sh`, `scripts/smoke_tests.py` |
| Tuân | Data Engineer | Testing, Data Quality | `dbt/models/`, `dbt/tests/`, `great_expectations/`, `scripts/run_airflow_quality_task.py` |
| Thịnh | Pipeline / Observability Engineer | Airflow, Monitoring, Incident Response | `airflow/dags/`, `scripts/health_check.py`, [airflow_pipeline.md](docs/airflow_pipeline.md), [incident_runbook.md](docs/incident_runbook.md) |

## 9. Demo

Buổi demo trình bày một quy trình DataOps liền mạch: mở pull request → CI kiểm tra → merge và
triển khai tự động → pipeline xử lý Bronze → Silver → Gold → monitoring ghi nhận và cảnh báo →
phát hiện sự cố và phục hồi. Kịch bản chi tiết nằm trong [docs/demo_guide.md](docs/demo_guide.md).
