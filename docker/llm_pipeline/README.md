# Điểm mount Docker

Thư mục này chỉ là điểm mount khi chạy chế độ phát triển (development mode).

Mã nguồn thật nằm ở: `../../llm_pipeline/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../llm_pipeline/` sẽ được mount vào `/app/llm_pipeline` trong container.

Bạn không cần chép mã nguồn vào thư mục này.

Tài liệu module đầy đủ: [`../../llm_pipeline/README.md`](../../llm_pipeline/README.md).

```text
../llm_pipeline (host) -> /app/llm_pipeline -> api container dùng pipeline
```
