# Tuần 3: deployment, smoke tests và rollback

Phạm vi ngày 11–14 theo kế hoạch nhóm: pre/post deployment checks, smoke tests,
khôi phục phiên bản dbt trước, kiểm tra secrets và chuẩn bị bằng chứng demo.
[Kết quả local ngày 18/11/2026](evidence/bao-week3/20261118/summary.json)
được chạy trên SQL Server dev; workflow đã sửa cần được xác nhận lại sau khi push.

## Chạy trên máy dev

Chạy từ thư mục gốc của repo. SQL Server phải có AdventureWorks2014 và login
trong `dbt/profiles.yml` phải kết nối được. DAG tự động cần tạm dừng khi kiểm thử
deploy/rollback để tránh hai lượt cùng ghi các bảng dbt.

```bash
# Chỉ dùng cho lần đầu, khi các bảng dbt chưa tồn tại.
SKIP_PRE_DEPLOY_TESTS=1 ./scripts/deploy.sh dev dev

# Các lần sau phải chạy cả pre-test và post-test.
./scripts/deploy.sh dev dev
```

Deploy thực hiện `deps → debug → compile → pre-test → run → post-test → smoke
→ docs`. Lần khởi tạo chỉ bỏ qua pre-test; post-test và smoke vẫn bắt buộc.
Lệnh chỉ trả 0 và tạo release trong `backups/dev_<timestamp>_<id>/` khi mọi
bước đạt. Mỗi release chứa source dbt cần cho `run/test`, `release.json` và
SHA-256 từng file. Không lưu `profiles.yml`, mật khẩu, `target/`, `logs/`
hay `dbt_packages/`. Các thư mục `backups/` được Git bỏ qua.

Smoke test kiểm tra 9 relations đại diện Bronze/Silver/Gold có dữ liệu và 7
khóa bắt buộc không NULL. Dataset AdventureWorks là dữ liệu lịch sử nên smoke
test không áp ngưỡng freshness 24 giờ; freshness có policy và báo cáo riêng.

## Khôi phục phiên bản trước

Chọn **release đã đạt trước lần deploy cần hoàn tác**, rồi chạy:

```bash
./scripts/rollback.sh dev backups/dev_<timestamp>_<id>
```

Script kiểm tra checksum và môi trường trước khi yêu cầu xác nhận. Nó chạy
`deps → debug → run → test → smoke` từ source trong release, dùng profile dev
hiện tại, không sửa mã nguồn đang mở. Có thể dùng `--yes` ở cuối trong bài
kiểm thử tự động. Các backup cũ chỉ chứa `target/` không đủ để rollback và
được từ chối.

Đây là **khôi phục phiên bản dbt**, không phải restore toàn bộ SQL Server:
những relation mới chỉ có trong bản lỗi sẽ không tự bị xóa, và thay đổi dữ
liệu ngoài dbt không được hoàn tác. Với thay đổi schema/data không tương thích
hoặc production, phải có bản backup database và kế hoạch restore riêng.
Bản release ghi lại Dockerfile/requirements để đối chiếu, nhưng rollback sử
dụng dbt CLI đang được cài trong môi trường hiện tại; cần kiểm tra tương thích
phiên bản trước khi khôi phục qua thay đổi runtime lớn.

## Staging và production

[Workflow deploy](../.github/workflows/deploy.yml) tạo SQL Server staging tạm
trên GitHub runner khi push vào `develop`. Nó chạy deploy cùng smoke test và
upload artifacts. Runner/database bị hủy sau job; artifact release không tạo
ra một staging server tồn tại lâu dài. Vì vậy rollback qua nhiều lần workflow
cần một database bền vững và tải lại release artifact cũ.

Production chỉ được phép chạy từ `main`, yêu cầu `PROD_SQL_SERVER`,
`PROD_SQL_USER`, `PROD_SQL_PASSWORD` từ GitHub environment secrets. Không
đưa mật khẩu vào tham số dòng lệnh của smoke test. Trước khi bật production,
cần cấu hình database thật, environment protection và backup SQL Server. Chưa
có production database để kiểm thử trong lượt triển khai này.

Kiểm tra secrets trong phần Bảo: workflow production dùng GitHub secrets,
staging tạo mật khẩu tạm và mask trong log, script không ghi credentials vào
release artifact. Repo hiện vẫn có thông tin đăng nhập demo cố định ở profile
dev và giá trị mặc định của Compose/staging profile từ phần thiết lập ban đầu.
Chỉ dùng chúng cho lab local; trước khi dùng môi trường chung cần chuyển sang
biến môi trường và đổi các mật khẩu đã từng xuất hiện trong Git history.

## Kiểm tra và demo

- Dev khởi tạo: 10 models, 202 dbt tests, 16 smoke checks đều đạt.
- Bản thử lỗi tạm làm rỗng `gold.gld_sales_summary`: smoke trả 1, phát hiện
  bảng rỗng. Mã nguồn repo không bị thay đổi.
- Rollback từ release cũ: 10 models, 202 tests, 16 smoke checks đạt, exit 0.
- Deploy dev bình thường sau khi đã có models: pre/post tests đều 202/202,
  10 models và 16 smoke checks đạt, exit 0.
- Kiểm tra đầu vào: thiếu production secrets, release sai môi trường, file
  release bị sửa và source thay đổi trong lúc deploy đều bị từ chối.

CI/CD đã sửa trong working tree; bằng chứng GitHub Actions cho commit mới
chỉ có sau khi Bảo commit/push và workflow chạy. Khi demo ngày 15, lưu URL của
PR/checks, staging deployment run và artifact release cùng kết quả rollback
trên môi trường thử nghiệm.
