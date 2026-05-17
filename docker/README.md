# Hướng dẫn Docker cho DATN

Container hóa hệ thống DATN với Docker Compose.

## Kiến trúc Container

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐        │
│  │    API      │◄───│   Neo4j     │    │   Ollama    │        │
│  │   (FastAPI) │    │  (GraphRAG) │    │    (LLM)    │        │
│  │   :8000     │    │   :7474     │    │   :7869     │        │
│  └──────┬──────┘    └─────────────┘    └─────────────┘        │
│         │                                                        │
│         └────────────────────────────────────────────────────►  │
│                                                                  │
│  ┌─────────────┐                                                │
│  │   Milvus    │  (Optional - disabled by default)             │
│  │  (Vector)   │                                                │
│  │  :19530     │                                                │
│  └─────────────┘                                                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Bắt đầu nhanh

### 1. Chạy production

```bash
# Build và chạy (từ thư mục docker/)
cd docker
docker-compose up --build

# Chạy background (detached)
docker-compose up -d

# Dừng
docker-compose down

# Dừng và xóa volumes
docker-compose down -v
```

### 2. Chạy development (hot-reload)

```bash
# Development với auto-reload (từ thư mục docker/)
cd docker
docker-compose -f docker-compose.yml -f docker-compose.override.yml up

# Hoặc shorthand
docker-compose up -d
 docker-compose -f docker-compose.override.yml up
```

## Các dịch vụ trong compose

| Service | Port | Mô tả |
|---------|------|-------|
| `api` | 8000 | Ứng dụng FastAPI |
| `neo4j` | 7474 (HTTP), 7687 (Bolt) | Cơ sở dữ liệu đồ thị |
| `ollama` | 7869 (map về 11434) | Container suy luận LLM |
| `milvus-standalone` | 19530 | Cơ sở dữ liệu vector (tùy chọn, mặc định tắt) |

## Sơ đồ luồng runtime Docker

```text
Trình duyệt/Client -> Container api:8000
                           |      |      |
                           v      v      v
                    neo4j:7687 ollama:11434 milvus:19530

Bind mounts (../api ../agent ../core ...) -> api container
Bind mounts (./graphrag ./upload ./config) -> api container
```

## Truy cập

- **Web UI**: http://localhost:8000/ui/
- **API Docs**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474 (user: `neo4j`, pass: `changeme`)
- **Milvus**: http://localhost:19530 (nếu bật profile milvus)

## Lệnh thường dùng

### Xem logs

```bash
# Tất cả services
 docker-compose logs -f

# Theo từng service
 docker-compose logs -f api
 docker-compose logs -f neo4j
```

### Chạy lệnh bên trong container

```bash
# Run agent CLI
 docker-compose exec api python -m agent --question "triệu chứng cảm cúm"

# Run tests
 docker-compose exec api pytest tests/ -v

# Bash shell
 docker-compose exec api bash
```

### Rebuild

```bash
# Sau khi thay đổi code
 docker-compose up --build api

# Hoặc chỉ rebuild
 docker-compose build api
```

## Môi trường

### Production (Dockerfile)
- Multi-stage build (builder → production)
- Non-root user (`app`)
- Health checks
- Không hot-reload

### Development (docker-compose.override.yml)
- Mount source code (hot-reload)
- Debug logging enabled
- Auto-reload on file changes
- Query logging (Neo4j)

## Volumes

| Volume | Mô tả |
|--------|-------|
| `neo4j-data` | Neo4j database files |
| `neo4j-logs` | Neo4j logs |
| `./ollama` | Ollama models data (bind mount) |
| `./graphrag` | GraphRAG index data (bind mount) |
| `./upload` | File uploads (bind mount) |
| `./config` | Config files (bind mount, read-only) |

### Note về các folder rỗng trong `docker/`

Các folder `agent/`, `api/`, `config/`, `core/`, etc. trong thư mục `docker/` là **mount points** cho development mode (`docker-compose.override.yml`). Source code thực sự nằm ở parent directory (`../agent`, `../api`, etc.) và được mount vào container khi chạy dev mode. Không cần copy code vào các folder này.

## Ollama Container Usage

### Pull model

```bash
# Từ host
curl http://localhost:7869/api/pull -d '{"model":"llama3.1:8b"}'

# Hoặc vào container
docker-compose exec ollama ollama pull llama3.1:8b
```

### List models

```bash
curl http://localhost:7869/api/tags
docker-compose exec ollama ollama list
```

## Profiles

### Chạy với Milvus (Vector DB)

```bash
docker-compose --profile milvus up
```

Services thêm: `etcd`, `minio`, `milvus-standalone`

## Troubleshooting

### Lỗi kết nối Ollama

Ollama chạy trong container `datn-ollama`. API container kết nối qua internal Docker network:

```
OLLAMA_HOST=http://ollama:11434
```

Nếu muốn dùng Ollama trên host (không khuyến khích), sửa `docker-compose.yml`:

```yaml
environment:
  - OLLAMA_HOST=http://host.docker.internal:11434
```

**Windows/Mac:** `host.docker.internal` hoạt động tự động.

**Linux:** Thêm vào service `api`:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### Lỗi permission

```bash
# Fix ownership
 docker-compose down
sudo chown -R $USER:$USER graphrag/ upload/
 docker-compose up
```

### Clean start

```bash
# Xóa tất cả và bắt đầu lại
 docker-compose down -v
 docker-compose up --build
```

## Dockerfile / compose (file trong thư mục)

| Thành phần | Mô tả |
|---|---|
| `Dockerfile` | Build image `api`: Python, cài dependencies, entrypoint uvicorn/`api.main:app`. |
| `docker-compose.yml` | Stack chính: `api`, `neo4j`, `ollama` (+ profile `milvus`). |
| `docker-compose.override.yml` | Dev: mount source từ `..` vào các path rỗng (`../api` → `./api`), hot-reload. |
| Thư mục con `agent/`, `api/`, … rỗng | **Mount point** trong dev — không phải copy mã nguồn; mã thật nằm ở parent repo. |

## Environment Variables

| Variable | Default | Mô tả |
|----------|---------|-------|
| `OLLAMA_HOST` | `http://ollama:11434` | Ollama container internal URL |
| `OLLAMA_MODEL` | `llama3.1:8b` | Default model |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j connection |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | `changeme` | Neo4j password |
| `LOG_LEVEL` | `INFO` | Logging level |

## Build Args

| Arg | Default | Mô tả |
|-----|---------|-------|
| `PYTHON_VERSION` | `3.11` | Python version |

---

*Yêu cầu: Docker ≥ 20.10, Docker Compose ≥ 2.0*
