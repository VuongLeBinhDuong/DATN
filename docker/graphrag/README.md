# Điểm mount Docker

Thư mục này là điểm mount dữ liệu GraphRAG.

Dữ liệu và workspace thật nằm ở: `../../graphrag/`

Khi chạy `docker-compose` với `docker-compose.override.yml`, thư mục `../../graphrag/` sẽ được mount vào `/app/graphrag` trong container (đọc/ghi).

Dùng để lưu cache và kết quả đầu ra của GraphRAG.

Tài liệu workspace: [`../../graphrag/README.md`](../../graphrag/README.md).

```text
../graphrag (host) -> /app/graphrag (read-write) -> api/query
```
