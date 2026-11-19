# Kiến trúc hệ thống DataOps

Sơ đồ dùng Mermaid (GitHub hiển thị trực tiếp). Mỗi phần ghi người phụ trách chính.

## 1. Tổng quan

```mermaid
flowchart LR
    dev([Developer]) -->|PR| gh[GitHub<br/>feature/* → develop → main]
    gh -->|CI: lint, dbt compile/run/test| ci[GitHub Actions]
    gh -->|push develop/main| cd[Deploy workflow<br/>deploy.sh + smoke + release]

    subgraph host[Docker Compose — máy dev]
        direction LR
        af[Airflow 2.7.1<br/>webserver + scheduler<br/>LocalExecutor]
        pg[(Postgres 13<br/>Airflow metadata)]
        dbt[dbt 1.8.7<br/>container]
        ge[GX 0.18.22<br/>ge-worker]
        mssql[(SQL Server 2019<br/>AdventureWorks2014<br/>bronze/silver/gold)]
        af --- pg
        af -->|docker exec<br/>run_airflow_quality_task.py| dbt
        af -->|docker exec| ge
        dbt -->|ODBC| mssql
        ge -->|SQLAlchemy| mssql
    end

    cd -.->|dbt run/test trên dev| dbt
    af -->|alerts| chat[[Slack / Discord / Teams<br/>webhook]]
    af -->|alerts.jsonl, metrics, latest.json| logs[(airflow/logs)]
    ops([On-call]) -->|health_check.py, runbook| host
```

| Lớp | Thành phần | Phụ trách |
| --- | --- | --- |
| Source control, CI/CD, deploy, rollback | `.github/workflows/*`, `scripts/deploy.sh`, `rollback.sh`, `smoke_tests.py` | Bảo |
| Transform + chất lượng dữ liệu | `dbt/models`, `dbt/tests`, `great_expectations/`, runner | Tuân |
| Orchestration, monitoring, incident | `airflow/dags`, `utils/`, `health_check.py`, runbook | Thịnh |

## 2. Dữ liệu: Bronze → Silver → Gold

```mermaid
flowchart LR
    src[(AdventureWorks2014<br/>Sales / Person / Production)] --> b[bronze<br/>4 views: brnz_*]
    b --> s[silver<br/>slvr_customers 19.820<br/>slvr_products 504<br/>slvr_sales_orders 121.317]
    s --> g[gold<br/>gld_customer_metrics<br/>gld_product_performance<br/>gld_sales_summary]
    s -. GX customer/order suites .-> q{{40 expectations}}
    b & s & g -. dbt tests .-> t{{202 tests}}
```

Chi tiết lineage và catalog test: [tuan_data_lineage.md](tuan_data_lineage.md), [tuan_test_catalog.md](tuan_test_catalog.md).

## 3. Các DAG

```mermaid
flowchart LR
    subgraph T[dbt_transform — 06:00 VN hằng ngày]
        cr[check_runtime] --> deps[dbt_deps] --> run[dbt_run] --> test[dbt_test] --> gv[ge_validate] --> docs[dbt_docs<br/>SLA 1h]
    end
    subgraph Q[ge_data_quality — mỗi 6 giờ / tay]
        w[wait_for_transform_idle] --> cr2[check_runtime] --> gv2[ge_validate] --> rep[publish_quality_report<br/>all_done]
    end
    subgraph M[dataops_monitoring — mỗi 30 phút]
        c1[check_services] & c2[check_pipeline] & c3[check_metrics] & c4[check_disk] --> pr[publish_report<br/>all_done]
    end
    T -. trạng thái run .-> c2
    T -. đang chạy? .-> w
```

| DAG | Mục đích | Khi fail |
| --- | --- | --- |
| `dbt_transform` | build + test + GX gate + docs | retry backoff; alert warning/critical |
| `ge_data_quality` | re-validate Silver giữa các lần build | alert critical có số expectation đạt/không đạt |
| `dataops_monitoring` | sức khỏe tổng thể | alert khi trạng thái đổi, nhắc lại sau 6 h, báo phục hồi |
| `dataops_timeout_drill` | diễn tập timeout (tay) | xác nhận runner dọn tiến trình |

## 4. Luồng observability

```mermaid
sequenceDiagram
    participant T as Task (BashOperator)
    participant R as run_airflow_quality_task.py
    participant C as dbt / ge-worker container
    participant CB as utils/callbacks.py
    participant A as utils/alerting.py
    participant W as Webhook (Slack…)
    T->>R: bash runner <action>
    R->>C: docker exec -e DATAOPS_PROCESS_MARKER=…
    C-->>R: exit 0 / 1 (dữ liệu) / 2 (thực thi)
    R-->>T: tóm tắt + task_summary.json (bằng chứng)
    alt success
        T->>CB: on_success → metrics task_success
    else fail, còn retry
        T->>CB: on_retry → metrics + warning
        CB->>A: send_alert(warning)
    else fail hẳn
        T->>CB: on_failure → metrics + critical
        CB->>A: send_alert(critical)
    end
    A->>W: POST (slack/discord/teams/generic)
    A->>A: alerts.jsonl (luôn ghi)
    Note over T,C: Timeout/clear → SIGTERM → runner kill tiến trình mang marker trong container
```

| Tín hiệu | Nơi lưu | Đọc bằng |
| --- | --- | --- |
| Task log + `DATAOPS_EVENT` | `airflow/logs/dag_id=…/run_id=…/task_id=…/attempt=N.log` | Airflow UI, `grep` |
| Bằng chứng dbt/GX | `great_expectations/uncommitted/airflow/<hash>/<task>/try-N-<uuid>/` | `task_summary.json`, `stdout.log` |
| Metrics | `airflow/logs/dataops_metrics/task_metrics.jsonl` | `summarize_metrics`, monitor |
| Alert | `airflow/logs/dataops_alerts/alerts.jsonl` + webhook/email | chat, health check |
| Trạng thái sức khỏe | `airflow/logs/dataops_monitoring/latest.json`, `history.jsonl` | health check, runbook |
| Báo cáo run | `scripts/airflow_run_report.py` | JSON cho bằng chứng |

## 5. CI/CD (Bảo)

```mermaid
flowchart LR
    f[feature/*] -->|PR| d[develop]
    d -->|PR| m[main]
    f -. push .-> q1[python-quality<br/>black, flake8, pylint]
    f -. push .-> q2[dbt-ci<br/>sqlfluff, flake8,<br/>SQL Server tạm: dbt run/test/docs]
    d -. PR .-> q3[pr-checks<br/>conventional title, size, conflict]
    d -->|push| dep[deploy.yml<br/>staging tạm + smoke + release artifact]
    m -->|push / dispatch| prod[deploy production<br/>GitHub environment: production]
```

Chi tiết deploy/rollback: [week3_deployment.md](week3_deployment.md).

## 6. Quyết định thiết kế chính

| Quyết định | Lý do |
| --- | --- |
| dbt và GX chạy trong container riêng, Airflow gọi bằng `docker exec` | giữ nguyên dependency graph của image Airflow chính thức; mỗi công cụ pin version riêng (Tuân) |
| Runner trả exit 1 = dữ liệu, 2 = thực thi | phân biệt lỗi cần sửa dữ liệu với lỗi hạ tầng; GX exit 1 không retry |
| `check_runtime` trước mọi bước | lỗi hạ tầng được báo rõ ràng và không chạm vào dữ liệu |
| Alert qua callback + monitor độc lập | callback báo lỗi của từng run; monitor phát hiện cả khi không có run nào chạy (service chết, scheduler dừng) |
| Monitor chỉ alert khi trạng thái đổi | một sự cố = một thông báo; có thông báo phục hồi |
| Mọi thứ observability dùng thư viện chuẩn, không bao giờ raise | không thêm dependency vào image; lỗi giám sát không làm hỏng pipeline |
| `catchup=False`, `max_active_runs=1` | dataset lịch sử; hai run cùng ghi bảng dbt là không an toàn |
