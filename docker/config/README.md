# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../config/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../config/` sẽ được mount vào `/app/config` trong container (chỉ đọc).

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../config/README.md`](../../config/README.md).

```text
../config (host) -> /app/config (read-only) -> core/settings.py
```
