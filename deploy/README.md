# Module Deploy

## Mục đích

`deploy/` chứa cấu hình triển khai tách rời cho từng dịch vụ (đặc biệt Neo4j và Milvus) và Dockerfile API thay thế.

## Thành phần

| File | Vai trò |
|---|---|
| `Dockerfile.api` | Dockerfile API tối giản phục vụ deploy |
| `docker-compose.neo4j.yml` | Compose khởi chạy Neo4j độc lập |
| `docker-compose.milvus.yml` | Compose khởi chạy Milvus stack độc lập |

## Khi nào dùng

- Dùng khi không chạy full stack ở `docker/docker-compose.yml`.
- Dùng cho môi trường cần tách lifecycle của Neo4j/Milvus riêng.

## Chi tiết artifact

| File | Nội dung kỹ thuật |
|---|---|
| `Dockerfile.api` | Multi-stage hoặc image tối giản cho chỉ FastAPI/API (tách khỏi compose stack đầy đủ nếu cần push registry riêng). |
| `docker-compose.neo4j.yml` | Chỉ Neo4j: port 7474/7687, volume dữ liệu, env mật khẩu. |
| `docker-compose.milvus.yml` | Stack Milvus etcd/minio/standalone hoặc tương đương — bật khi cần vector ngoài compose chính. |

## Ví dụ lệnh

```bash
docker compose -f deploy/docker-compose.neo4j.yml up -d
docker compose -f deploy/docker-compose.milvus.yml up -d
```

## Cần cải thiện

1. Đồng bộ env variables với stack chính trong `docker/`.
2. Thêm profile theo môi trường (dev/staging/prod).
3. Bổ sung hướng dẫn migration dữ liệu khi nâng phiên bản.

## Sơ đồ luồng triển khai tách dịch vụ

```text
Người vận hành
   |         |             |
   v         v             v
docker-compose.neo4j.yml  docker-compose.milvus.yml  Dockerfile.api
   |                         |                         |
   v                         v                         v
 Neo4j                     Milvus                  Image API
                                                      |
                                                      v
                                                Container API
                                                   |      |
                                                   v      v
                                                 Neo4j  Milvus
```

## Liên kết

- Docker stack chính: [`../docker/README.md`](../docker/README.md)
- README tổng: [`../README.md`](../README.md)
