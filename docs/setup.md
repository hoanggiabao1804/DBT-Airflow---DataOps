# Cài đặt và chạy thử trên máy mới

Hướng dẫn này dùng **Docker Compose và Bash** tại thư mục gốc repository.
Docker chạy SQL Server, dbt, Airflow, PostgreSQL và GE; không cần cài dbt/ODBC
trên máy host. Cần Git, Docker Engine/Desktop với Compose v2, quyền dùng
Docker, đủ RAM cho SQL Server + Airflow và cổng `1433`, `8080` còn trống.

## 1. Lấy code và chọn cấu hình Compose

```bash
git clone https://github.com/hoanggiabao1804/DBT-Airflow---DataOps.git dbt_airflow_project
cd dbt_airflow_project
git switch develop
export COMPOSE_PROJECT_NAME=dbt_airflow_project
export AIRFLOW_UID="$(id -u)"
export DOCKER_GID="$(stat -c '%g' /var/run/docker.sock)" # Linux; Docker Desktop có thể dùng 0
mkdir -p airflow/logs great_expectations/uncommitted
```

`COMPOSE_PROJECT_NAME` giữ tên container ổn định cho runner của DAG.
`DOCKER_GID` cho phép Airflow gọi dbt/GE qua Docker socket trên Linux.
Đặt các biến này trong **cùng terminal** dùng cho các lệnh Compose bên dưới.
Trên Windows, chạy hướng dẫn Bash này trong WSL với Docker Desktop WSL
integration; nếu dùng PowerShell trực tiếp, cần chuyển cú pháp `export`,
`$(...)` và SQL heredoc. `DOCKER_GID` thường dùng giá trị mặc định 0 trên
Docker Desktop.

Các lệnh tiếp theo dùng Compose gốc **cùng overlay chất lượng**. Overlay thêm
`ge-worker`, mount scripts/evidence và khởi tạo metadata Airflow; dùng nó để
thử DAG `dbt_transform` đầy đủ. Nếu chỉ thử dbt, Compose gốc là đủ.

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml ps
```

Chờ `postgres`, `ge-worker`, `airflow-webserver` và `airflow-scheduler` healthy;
`airflow-init` hoàn thành rồi thoát là bình thường. Build lần đầu có thể lâu
vì tải SQL Server, AdventureWorks và Python packages.

## 2. Restore AdventureWorks và tạo login dev

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml \
  exec -T sqlserver /tmp/restore_db.sh
```

Lệnh restore ghi đè database `AdventureWorks2014` trong volume local; chỉ dùng
khi tạo môi trường mới hoặc muốn làm mới dữ liệu mẫu. Target `dev` trong
[`dbt/profiles.yml`](../dbt/profiles.yml) dùng login demo `imrandbtnew`. Tạo
login đó một lần, với password **đúng như profile dev trong checkout này**:

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml \
  exec -T sqlserver bash -lc \
  '/opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "$SA_PASSWORD" -b' <<'SQL'
IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'imrandbtnew')
    CREATE LOGIN [imrandbtnew] WITH PASSWORD = N'Imran@12345';
GO
USE [AdventureWorks2014];
GO
IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'imrandbtnew')
    CREATE USER [imrandbtnew] FOR LOGIN [imrandbtnew];
GO
IF IS_ROLEMEMBER(N'db_owner', N'imrandbtnew') = 0
    ALTER ROLE [db_owner] ADD MEMBER [imrandbtnew];
GO
SQL
```

Các giá trị này chỉ dành cho lab local. Trước khi dùng database chung hoặc
production, thay credentials demo và cấp quyền tối thiểu phù hợp. Không
commit `.env.dev`, `.env.staging`, `.env.prod` hoặc log chứa mật khẩu.

## 3. Chạy dbt và kiểm tra dữ liệu

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T dbt dbt debug
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T dbt dbt deps
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T dbt dbt run
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml exec -T dbt dbt test
```

Khi source database đã được restore và profile kết nối được, checkout hiện có
10 dbt models và 202 data tests. **Chạy `dbt run` trước `dbt test`** trên
database mới; `dbt test` tự nó không tạo các bảng/view Bronze–Gold.

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml \
  exec -T ge-worker python /workspace/scripts/run_ge_checkpoints.py \
  --target dev --schema silver \
  --output-dir "/evidence/manual-$(date -u +%Y%m%dT%H%M%SZ)"
```

Hai GE checkpoints kiểm tra customer/order Silver, tổng 40 expectations.
Kết quả nằm trong `great_expectations/uncommitted/manual-*/` trên host.

## 4. Kiểm tra Airflow và tài liệu model

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml \
  exec -T airflow-scheduler airflow dags list-import-errors
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml \
  exec -T airflow-scheduler airflow dags list
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml \
  exec -T airflow-scheduler airflow dags test dbt_transform
```

Lệnh cuối chạy đủ `deps → run → test → GE → docs`; không chạy đồng thời với
một lượt deploy/rollback khác. DAG mặc định paused để tránh chạy tự động trên
bộ dữ liệu lịch sử. Airflow UI ở `http://localhost:8080`; tài khoản lab mặc
định do Compose overlay tạo là `admin`/`admin`, trừ khi bạn đổi biến
`AIRFLOW_ADMIN_*`. dbt docs sinh ra trong `dbt/target/` sau bước `docs`.

`dbt source freshness` là kiểm tra **riêng**: sáu nguồn lịch sử có
`ModifiedDate` từ 2008–2015 nên dự kiến `ERROR STALE` và exit 1 với SLA demo
24/48 giờ. Xem [model reference](model_reference.md#source-freshness).

## 5. Dừng dịch vụ

```bash
docker compose -f docker-compose.yml -f docker-compose.airflow-quality.yml down
```

Lệnh `down` giữ lại volumes dữ liệu. Không dùng `down -v` nếu muốn giữ
AdventureWorks đã restore và metadata Airflow. Xem [troubleshooting](troubleshooting.md)
khi một bước không đạt.
