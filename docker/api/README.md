# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../api/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../api/` sẽ được mount vào `/app/api` trong container.

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../api/README.md`](../../api/README.md).

```text
../api (host) -> /app/api (container) -> Container api
```
