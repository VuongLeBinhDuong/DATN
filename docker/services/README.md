# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../services/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../services/` sẽ được mount vào `/app/services` trong container.

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../services/README.md`](../../services/README.md).

```text
../services (host) -> /app/services -> api/routes gọi service
```
