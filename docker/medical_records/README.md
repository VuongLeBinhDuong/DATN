# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../medical_records/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../medical_records/` sẽ được mount vào `/app/medical_records` trong container.

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../medical_records/README.md`](../../medical_records/README.md).

```text
../medical_records (host) -> /app/medical_records -> /api/medical-record/*
```
