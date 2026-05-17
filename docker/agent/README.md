# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../agent/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../agent/` sẽ được mount vào `/app/agent` trong container.

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../agent/README.md`](../../agent/README.md).

```text
../agent (host) -> /app/agent (container) -> api container dùng agent
```
