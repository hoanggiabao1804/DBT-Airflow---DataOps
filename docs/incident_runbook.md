# Incident runbook — DataOps pipeline

Dùng khi nhận alert (Slack/Discord/email hoặc `airflow/logs/dataops_alerts/alerts.jsonl`),
khi health check báo `WARN/FAIL`, hoặc khi ai đó báo "số liệu Gold sai". Mỗi alert có dòng
`Runbook: docs/incident_runbook.md` dẫn về đây.

Quy ước trong tài liệu:

```bash
DC="docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml"
AF="$DC exec -T airflow-scheduler airflow"
```

## 0. Năm phút đầu tiên

1. **Xác nhận** đã nhận alert trong kênh nhóm ("Thịnh đang xử lý") — tránh hai người cùng sửa.
2. **Chạy health check**:
   ```bash
   python3 scripts/health_check.py            # exit 0 OK, 1 WARN, 2 FAIL; --json để lưu
   ```
3. **Phân loại mức độ** theo bảng dưới, ghi giờ bắt đầu vào
   [incident template](incident_template.md) (copy thành `docs/incidents/YYYYMMDD-<tên>.md`).
4. **Ngăn lan rộng** nếu dữ liệu sai có thể bị dùng tiếp: pause DAG
   (`$AF dags pause dbt_transform`) và báo nhóm không dùng Gold cho tới khi xử lý xong.
5. Đi tới mục tương ứng ở phần 2.

| Mức | Khi nào | Ví dụ | Phản hồi |
| --- | --- | --- | --- |
| **SEV1** | Dữ liệu sai đã/đang được dùng, hoặc mất dữ liệu | Gold sai số liệu; bảng bị xóa | ngay lập tức, cả nhóm |
| **SEV2** | Pipeline dừng, dữ liệu cũ nhưng đúng | `dbt_transform` fail; SQL Server down | trong buổi làm việc |
| **SEV3** | Suy giảm, chưa ảnh hưởng dữ liệu | retry warning; disk < 5 GB; monitor WARN | trong ngày |

## 1. Bảng tra nhanh: alert → mục xử lý

| Alert / triệu chứng | Mục |
| --- | --- |
| `Task failed: dbt_transform.check_runtime` | [2.1 Hạ tầng](#21-hạ-tầng-container-sql-server) |
| `DataOps health CRITICAL: services=…` | [2.1 Hạ tầng](#21-hạ-tầng-container-sql-server) |
| `Task failed: dbt_transform.dbt_run` | [2.2 dbt run lỗi](#22-dbt_run-lỗi) |
| `Task failed: dbt_transform.dbt_test` | [2.3 Test dữ liệu lỗi](#23-dbt_test-hoặc-ge-lỗi-chất-lượng-dữ-liệu) |
| `Data quality FAILED on …` / `ge_validate` fail | [2.3 Test dữ liệu lỗi](#23-dbt_test-hoặc-ge-lỗi-chất-lượng-dữ-liệu) |
| `Task failed: dbt_transform.dbt_deps` | [2.4 dbt deps](#24-dbt_deps-lỗi) |
| `DAG run failed: … timed_out`, task chạy mãi | [2.5 Treo / timeout](#25-task-treo-timeout-tiến-trình-mồ-côi) |
| health check `orphans` WARN | [2.5 Treo / timeout](#25-task-treo-timeout-tiến-trình-mồ-côi) |
| `pipeline=last success … h ago` | [2.6 Pipeline không chạy](#26-pipeline-không-chạy-theo-lịch) |
| `SLA missed: dbt_transform` | [2.6 Pipeline không chạy](#26-pipeline-không-chạy-theo-lịch) |
| `disk=… GB free` | [2.7 Hết dung lượng](#27-hết-dung-lượng-đĩa) |
| Lỗi sau khi deploy bản mới | [2.8 Lỗi do deploy](#28-lỗi-sau-deploy-rollback) |
| DAG biến mất khỏi UI | [2.9 Lỗi import DAG](#29-dag-không-xuất-hiện--lỗi-import) |

## 2. Quy trình theo loại sự cố

### 2.1 Hạ tầng: container, SQL Server

**Dấu hiệu**: `check_runtime` in `Service X: expected 1 running container, found 0` hoặc
`dbt debug: FAILED … SQL Server down`; health check `services`/`sqlserver` FAIL.

```bash
$DC ps                                   # service nào không "Up"?
$DC logs --tail 100 sqlserver            # hoặc dbt / ge-worker / airflow-scheduler
$DC up -d sqlserver dbt ge-worker        # khởi động lại phần bị dừng
python3 scripts/health_check.py          # chờ tới khi sqlserver = ONLINE, dbt OK
```

- SQL Server mất ~20–60 s để nhận kết nối sau khi start; `dbt debug` lỗi trong lúc đó là bình thường.
- Nếu `AdventureWorks2014 missing` (volume mới): `$DC exec sqlserver /tmp/restore_db.sh`, tạo lại login
  dbt theo `0. NEW_COMPUTER_SETUP.md`.
- **Phục hồi pipeline**: clear task lỗi để chạy tiếp từ chỗ dừng (không cần chạy lại từ đầu):
  ```bash
  $AF tasks clear dbt_transform -t check_runtime -d -y -s <ngày-logical> -e <ngày-logical>
  # hoặc trên UI: Grid → task đỏ → Clear → "Downstream" ✔
  ```

### 2.2 `dbt_run` lỗi

1. Xem log tóm tắt trong Airflow (dòng `dbt_run: failed, native exit 1 … Evidence: …`).
2. Mở log đầy đủ: `great_expectations/uncommitted/airflow/<hash>/dbt_run/try-<n>-<uuid>/stdout.log`
   và `run_results.json` → tìm model `error`.
3. Thường gặp: lỗi SQL sau khi đổi model (→ 2.8 nếu vừa deploy), quyền của login dbt, bảng nguồn mất.
4. Sửa trên nhánh `fix/...`, PR, CI pass → merge → deploy; hoặc rollback (2.8). **Không** sửa
   trực tiếp trong container.

### 2.3 `dbt_test` hoặc GE: lỗi chất lượng dữ liệu

Đây là **dữ liệu sai**, không phải hạ tầng → retry không giúp ích. Pipeline đã tự chặn
`dbt_docs`, Gold mới **chưa được công bố** nhưng bảng Silver/Gold đã được ghi bởi `dbt_run`.

1. Mức độ: SEV2; nâng SEV1 nếu Gold sai đã được dùng.
2. Xác định test/expectation lỗi:
   - dbt: `…/dbt_test/try-*/run_results.json` (status `fail`), `stdout.log`.
   - GE: alert ghi rõ `customer_checkpoint: 9/10 expectations passed`; chi tiết ở
     `…/ge_validate/try-*/ge/summary.json` (`rule_id`, `unexpected_count`).
3. Kiểm tra lại độc lập, không chờ lịch: trigger `ge_data_quality` (có thể đổi `schema`).
   ```bash
   $AF dags trigger ge_data_quality --conf '{"schema": "silver"}'
   ```
4. Nguyên nhân: dữ liệu nguồn thay đổi → báo Tuân (owner tests); model sai → 2.2/2.8.
5. Khi dữ liệu đúng trở lại: chạy lại `dbt_transform` đầy đủ; xác nhận `dbt_docs` success.

### 2.4 `dbt_deps` lỗi

Cần mạng tới hub.getdbt.com/GitHub. Đã có 3 retries với backoff. Nếu vẫn lỗi: kiểm tra mạng
của Docker (`$DC exec dbt curl -sI https://hub.getdbt.com`), `dbt/packages.yml`, `package-lock.yml`.
Có thể chạy tiếp từ `dbt_run` vì `dbt_packages/` từ lần trước vẫn còn (clear `dbt_run` downstream).

### 2.5 Task treo, timeout, tiến trình mồ côi

Airflow giết tiến trình `docker exec` khi timeout/clear, nhưng **tiến trình dbt/GX bên trong
container có thể vẫn chạy** (đã ghi nhận ở tuần 3 của Tuân). Retry trong lúc đó sẽ có hai dbt
cùng ghi một bảng.

```bash
python3 scripts/health_check.py --skip-dbt     # dòng orphans
$DC exec dbt sh -c 'for p in /proc/[0-9]*; do printf "%s " "${p#/proc/}"; tr "\0" " " < $p/cmdline; echo; done' | grep "bin/dbt "
$DC exec dbt kill <pid>                         # dừng tiến trình mồ côi
```

Sau đó mới clear/retry task. Từ ngày 13, runner tự dừng tiến trình trong container khi task bị
kill (`task_summary.json`: `status: killed`, `killed_container_processes`) — xem
[thinh_week3_day13.md](thinh_week3_day13.md); các lệnh trên là phương án dự phòng khi runner bị
`SIGKILL` (không kịp dọn).

### 2.6 Pipeline không chạy theo lịch

```bash
$AF dags list | grep dbt_transform              # paused = True?
$AF dags next-execution dbt_transform
$DC exec -T airflow-scheduler env | grep DATAOPS_SCHEDULE   # "manual" tắt lịch
curl -s localhost:8080/health                   # scheduler heartbeat
```

Nguyên nhân thường gặp: DAG bị pause sau khi test deploy, scheduler chết, run trước treo giữ
slot (`max_active_runs=1`) → 2.5.

### 2.7 Hết dung lượng đĩa

Bằng chứng mỗi lần chạy nằm ở `great_expectations/uncommitted/airflow/` và log ở `airflow/logs/`.

```bash
du -sh great_expectations/uncommitted/airflow airflow/logs dbt/target
find great_expectations/uncommitted/airflow -mindepth 1 -maxdepth 1 -mtime +14 -exec rm -rf {} +
find airflow/logs -name '*.log' -mtime +14 -delete
docker system df && docker image prune -f
```

Không xoá bằng chứng của sự cố đang điều tra hoặc đã đưa vào báo cáo.

### 2.8 Lỗi sau deploy: rollback

Nếu lỗi bắt đầu ngay sau merge/deploy: ưu tiên **rollback trước, điều tra sau**.

```bash
$AF dags pause dbt_transform
ls -1d backups/dev_* | tail -5                  # chọn release ĐẠT trước lần deploy lỗi
./scripts/rollback.sh dev backups/dev_<timestamp>_<id>
$AF dags unpause dbt_transform
$AF dags trigger dbt_transform --run-id rollback-verify-$(date -u +%Y%m%dT%H%M%SZ)
```

Chi tiết và giới hạn (rollback chỉ khôi phục phiên bản dbt, không restore database):
[week3_deployment.md](week3_deployment.md) (Bảo).

### 2.9 DAG không xuất hiện / lỗi import

```bash
$AF dags list-import-errors
$DC logs --tail 50 airflow-scheduler
python -m pytest airflow/tests -q               # utils còn import được không?
```

Lỗi import thường do commit DAG chưa qua CI. Revert commit hoặc sửa nhanh qua PR.

## 3. Kết thúc sự cố

1. Pipeline chạy lại thành công: `dbt_transform` 6/6 success, `ge_data_quality` success.
2. `python3 scripts/health_check.py` → `OVERALL: OK`; monitor gửi alert `recovered`. Nếu sự cố không
   do monitor phát hiện (ví dụ lỗi dữ liệu, timeout), đóng chính thức để `alerts_24h` hết WARN:
   `python3 scripts/health_check.py --resolve "INC-YYYYMMDD-NN <tóm tắt>"`.
3. Unpause các DAG đã pause; báo nhóm dữ liệu dùng lại được.
4. Hoàn thành [incident template](incident_template.md): timeline, nguyên nhân gốc (5 Whys),
   hành động phòng ngừa có người phụ trách + hạn. Viết **blameless** — mô tả hệ thống, không đổ lỗi người.
5. Tạo issue GitHub cho từng hành động phòng ngừa.

## 4. Liên hệ và phân công

| Mảng | Người phụ trách |
| --- | --- |
| Airflow, monitoring, alert, runbook (incident commander mặc định) | Thịnh |
| dbt models, tests, Great Expectations | Tuân |
| Git, CI/CD, deploy, rollback, secrets | Bảo |
