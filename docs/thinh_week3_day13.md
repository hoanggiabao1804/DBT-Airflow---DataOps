# Thịnh — Tuần 3, ngày 13: kiểm tra failure/retry/alert, chạy E2E cùng nhóm

Ngày 13 làm hai việc: (1) sửa các điểm yếu tìm ra từ diễn tập ngày 10 và vấn đề Tuân bàn giao
(tiến trình mồ côi khi task bị hủy), kiểm chứng lại từng cái bằng lỗi thật; (2) chạy E2E toàn
nhóm: deploy của Bảo → pipeline + tests/GE của Tuân → monitoring/health check của Thịnh.

## 1. Tiến trình mồ côi khi task bị kill (bàn giao từ Tuân)

**Vấn đề.** Airflow hủy task (timeout, mark failed, clear) bằng SIGTERM tới process group của
BashOperator. Runner chỉ giết được client `docker exec` cục bộ; tiến trình `dbt`/GX **bên trong
container** chạy tiếp. Nếu sau đó retry, hai dbt cùng ghi một bảng.

**Tái hiện** (`setsid` chạy runner như BashOperator, rồi `kill -TERM -<pgid>` như `on_kill`):

```text
before kill: 1 dbt test process(es)
after kill+3s: 1 dbt test process(es)        ← tiến trình mồ côi
runner output:                                 ← runner chết, không ghi kết quả
```

**Sửa** trong `scripts/run_airflow_quality_task.py` (file của Tuân, phần cancellation):

1. Mỗi lệnh `docker exec` được gắn biến `DATAOPS_PROCESS_MARKER=<uuid>` riêng của lần chạy.
2. Runner đăng ký handler SIGTERM → ném `Terminated`.
3. Khi bắt `Terminated`: chạy trong container một shell quét `/proc/*/environ`, `kill -TERM` mọi
   tiến trình mang đúng marker đó (shell quét không có marker nên không tự giết mình), ghi
   `task_summary.json` với `status: killed`, `exit_code: 143`, `killed_container_processes`.

```text
before kill: 1 dbt test process(es)
after kill+3s: 0 dbt test process(es)
dbt_test: killed, native exit None, final exit 143. Evidence: …
```

**Kiểm chứng trên Airflow thật** — DAG diễn tập mới `dataops_timeout_drill` (`drill_dag.py`,
chạy tay, mặc định pause): `dbt test` thật (~9 s) với `execution_timeout=5s`.

| Bước | Kết quả |
| --- | --- |
| Airflow | `Process timed out` → `Sending SIGTERM signal to process group` → `Marking task as FAILED` |
| Runner | `status: killed`, `killed_container_processes: 2`; dbt dừng ở test 96/202 (`context canceled`) |
| Container dbt sau đó | 0 tiến trình dbt |
| Alert | critical `Task failed: dataops_timeout_drill.dbt_test_with_timeout`, không retry (`retries=0`) |

Bằng chứng: [orphan_before_fix.txt](evidence/thinh-week3-day13/20261119/orphan_before_fix.txt),
[orphan_after_fix.txt](evidence/thinh-week3-day13/20261119/orphan_after_fix.txt),
[timeout_drill_airflow_log.txt](evidence/thinh-week3-day13/20261119/timeout_drill_airflow_log.txt),
[timeout_drill_task_summary.json](evidence/thinh-week3-day13/20261119/timeout_drill_task_summary.json).

Giới hạn: nếu runner bị `SIGKILL` (Airflow gửi sau `killed_task_cleanup_time`=60 s), handler không
chạy; health check (`orphans`) và runbook 2.5 là lớp dự phòng.

## 2. Lỗi dữ liệu không retry

**Vấn đề (ngày 10).** GX exit 1 (expectation fail) vẫn retry: thêm ~2 phút và một alert warning vô ích.

**Sửa.** `utils/operators.py` — `QualityStepOperator(BashOperator)` với `no_retry_exit_codes`: nếu
exit code nằm trong danh sách, ném `AirflowFailException` → fail ngay, callback/alert vẫn chạy.
Áp dụng exit 1 cho `ge_validate` ở cả `dbt_transform` và `ge_data_quality`. **Không** áp dụng cho
bước dbt vì dbt cũng trả 1 khi lỗi kết nối database (có thể tự hết khi retry).

| | Ngày 10 (trước) | Ngày 13 (sau) |
| --- | --- | --- |
| `ge_validate` trên `dq_drill` | 2 attempts, warning + critical | **1 attempt**, chỉ critical |
| Thời gian DAG run | ~2 phút 10 s | **16 s** |
| Log | — | `AirflowFailException: Exit code 1 is a deterministic failure; not retrying.` |

Bằng chứng: [dq_no_retry_run.json](evidence/thinh-week3-day13/20261119/dq_no_retry_run.json).

## 3. Các cải tiến nhỏ khác

| Phát hiện | Sửa | Kiểm chứng |
| --- | --- | --- |
| Log `check_runtime` in nguyên script bash (dòng `Running command`) | tách thành `scripts/check_runtime.sh` | log còn `Running command: ['/bin/bash', '-c', 'bash …/check_runtime.sh ']` — [check_runtime_new_log.txt](evidence/thinh-week3-day13/20261119/check_runtime_new_log.txt) |
| SQL Server chết → `dbt debug` chờ ~65 s mỗi attempt | `timeout 30` | fail sau đúng 30 s |
| Title alert monitor lặp lại toàn bộ chi tiết | title chỉ liệt kê tên check (`services, pipeline`), chi tiết ở message | unit test mới (28 tests) |
| Diễn tập xong, `alerts_24h` WARN mãi vì không có "recovered" | `health_check.py --resolve "<ghi chú>"` ghi alert `Incident resolved` | [after_resolve](evidence/thinh-week3-day13/20261119/team_e2e_health_check_after_resolve.txt) |

Báo cáo sự cố mẫu theo template: [incidents/20261119-sqlserver-outage-drill.md](incidents/20261119-sqlserver-outage-drill.md).

## 4. E2E cùng nhóm (19/11/2026)

| Bước | Thành viên | Kết quả |
| --- | --- | --- |
| Pause `dbt_transform` (theo `week3_deployment.md`) | — | ✅ |
| `./scripts/deploy.sh dev dev` | Bảo | ✅ pre-test 202/202, run 10/10, post-test 202/202, smoke 16/16, release được tạo — [team_e2e_deploy.txt](evidence/thinh-week3-day13/20261119/team_e2e_deploy.txt) |
| Unpause, `dbt_transform` `thinh-week3-day13-team-e2e` | Thịnh + Tuân | ✅ 6/6, 42,4 s |
| `ge_data_quality` `thinh-week3-day13-team-e2e-ge` | Tuân + Thịnh | ✅ 4/4, 40/40 expectations |
| `dataops_monitoring` `thinh-week3-day13-team-e2e-monitor` | Thịnh | ✅ OVERALL OK |
| `health_check.py` | Thịnh | WARN (2 alert diễn tập chưa đóng) → `--resolve` → **OK** |

## Ma trận kịch bản lỗi đã kiểm thử (ngày 6–13)

| # | Kịch bản | Phát hiện bởi | Retry | Alert | Phục hồi |
| --- | --- | --- | --- | --- | --- |
| 1 | `ge-worker` dừng | `check_runtime`, monitor, health check | 2 retry backoff | warning ×2, critical | start container, clear task |
| 2 | SQL Server dừng | `check_runtime`, monitor, health check | 2 retry backoff | warning ×2, critical ×2, recovered | start, rerun |
| 3 | Dữ liệu sai (GX exit 1) | `ge_validate` | **không** (từ ngày 13) | 1 critical có chi tiết | sửa dữ liệu/model |
| 4 | Task treo → timeout | Airflow `execution_timeout` | theo cấu hình | critical | runner tự dọn container |
| 5 | Tiến trình mồ côi | health check `orphans` | — | WARN | runbook 2.5 |
| 6 | Đổi sang trạng thái tốt | monitor | — | info `recovered` | — |
