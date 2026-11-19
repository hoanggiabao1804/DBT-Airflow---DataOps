# Thịnh — Tuần 1, ngày 5: chạy DAG end-to-end và ghi nhận kết quả

Run `thinh-week1-day5-e2e-01` được trigger thủ công và chạy bởi **scheduler/LocalExecutor**
(không phải `airflow dags test`) trên DAG đã cải tiến ở [ngày 3–4](thinh_week1_day3_4.md).

```bash
$DC exec -T airflow-scheduler airflow dags trigger dbt_transform --run-id thinh-week1-day5-e2e-01
$DC exec -T airflow-scheduler python /opt/airflow/scripts/airflow_run_report.py dbt_transform thinh-week1-day5-e2e-01
```

## Kết quả

Trạng thái DAG run: **success**, 42,7 giây, mọi task thành công ngay lần đầu
([e2e_run.json](evidence/thinh-week1-day5/20261119/e2e_run.json)).

| Task | Trạng thái | Lần thử | Thời gian (s) | Kết quả bên trong |
| --- | --- | ---: | ---: | --- |
| check_runtime | success | 1 | 2,8 | dbt + ge-worker chạy, `dbt debug` OK |
| dbt_deps | success | 1 | 4,1 | packages cài xong |
| dbt_run | success | 1 | 6,9 | 10/10 models `success` |
| dbt_test | success | 1 | 8,7 | 202/202 `pass` |
| ge_validate | success | 1 | 8,3 | 2 checkpoints, 40/40 expectations |
| dbt_docs | success | 1 | 6,8 | `catalog.json`, `index.html` đã tạo |

Nguồn: [task_summaries.json](evidence/thinh-week1-day5/20261119/task_summaries.json) (trích từ
`task_summary.json` của runner) và
[task_log_summary_lines.txt](evidence/thinh-week1-day5/20261119/task_log_summary_lines.txt)
(dòng tóm tắt trong Airflow log).

Số dòng sau khi chạy ([layer_row_counts.txt](evidence/thinh-week1-day5/20261119/layer_row_counts.txt)):

| Silver | Dòng | Gold | Dòng |
| --- | ---: | --- | ---: |
| slvr_customers | 19.820 | gld_customer_metrics | 19.820 |
| slvr_products | 504 | gld_product_performance | 504 |
| slvr_sales_orders | 121.317 | gld_sales_summary | 1.124 |

Bronze là view nên không có trong thống kê `sys.partitions`.

## So sánh với baseline

| | Baseline ngày 1–2 | Ngày 5 |
| --- | --- | --- |
| Số task | 5 | 6 (thêm `check_runtime`) |
| Thời gian run | 41,3 s | 42,7 s (+2,8 s cho preflight) |
| Chạy theo lịch | không | có — run `scheduled__2026-11-17T23:00:00+00:00` thành công |
| Retry | 1 lần, cố định | 1–3 lần theo task, backoff |

## Checkpoint tuần 1 (phần của Thịnh)

| Tiêu chí | Trạng thái |
| --- | --- |
| Containers chạy, SQL Server có AdventureWorks2014 | ✅ |
| DAG xuất hiện trong Airflow và chạy end-to-end | ✅ manual + scheduled |
| `airflow/dags/dbt_dag.py`, `docs/airflow_pipeline.md` | ✅ |

## Nhận xét / việc tuần 2

- Khi một task fail, hiện **không ai được báo** — phải mở UI mới thấy. → Module 4.
- Chưa có số liệu lịch sử (tỉ lệ thành công, thời gian từng task theo ngày) ngoài metadata
  DB của Airflow. → metrics file + monitoring DAG.
