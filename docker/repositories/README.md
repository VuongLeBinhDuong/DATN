# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../repositories/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../repositories/` sẽ được mount vào `/app/repositories` trong container.

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../repositories/README.md`](../../repositories/README.md).

```text
../repositories (host) -> /app/repositories -> agent/services query
```
