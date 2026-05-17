# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../core/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../core/` sẽ được mount vào `/app/core` trong container.

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../core/README.md`](../../core/README.md).

```text
../core (host) -> /app/core (container) -> api/services trong container
```
