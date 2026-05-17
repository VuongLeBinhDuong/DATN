# Module API

## Mục đích

`api/` là lớp trình bày (presentation layer) của hệ thống:

- Nhận request HTTP.
- Kiểm tra dữ liệu đầu vào (validate input).
- Gọi service/repository phù hợp.
- Trả về JSON hoặc NDJSON stream.

## Cấu trúc

| File | Vai trò |
|---|---|
| `main.py` | FastAPI app factory, CORS, static mount, include routers |
| `dependencies.py` | Dependency injection (settings, repo, service, rate-limit) |
| `routes/` | Các route module theo nhóm chức năng |

### Route modules

| File | Endpoint chính |
|---|---|
| `routes/health.py` | `/`, `/health`, `/health/ready`, `/health/config`, `/health/performance` |
| `routes/graphrag.py` | `/ask`, `/api/query` |
| `routes/agent.py` | `/api/agent-query`, `/api/agent-query/stream`, `/api/langchain-graph-query*` |
| `routes/ollama.py` | `/api/ollama/health`, `/api/ollama/chat` |

## Chạy local API

```bash
python -m uvicorn api.main:app --reload
```

Sau khi chạy:

- UI: `http://localhost:8000/ui/`
- Swagger: `http://localhost:8000/docs`

## Nguyên tắc thiết kế hiện tại

- Route mỏng, không nhồi business logic.
- Logic phức tạp đặt ở `services/`, `agent/`, `medical_records/`.
- Cấu hình tập trung ở `core/settings.py`.

## Biến cấu hình liên quan

- `CORS_ORIGINS`
- `RATE_WINDOW_SEC`
- `RATE_MAX_PER_WINDOW`
- `EXPOSE_RETRIEVAL_DEBUG`
- Toàn bộ nhóm `OLLAMA_*`, `NEO4J_*`, `AGENT_*`

## Cần cải thiện

1. Chuẩn hóa response envelope cho tất cả endpoint (status, trace_id, error_code).
2. Thêm OpenAPI examples đầy đủ cho từng endpoint quan trọng.
3. Thêm contract tests kiểm tra backward compatibility endpoint.

## Sơ đồ luồng request trong API

```text
+-------------+      +----------------------+
| Client / UI | ---> |  api/routes/*.py     |
+-------------+      +----------------------+
                          |         |
                          v         v
                  +----------------------+     +---------------------------+
                  | api/dependencies.py  | --> | services/*                |
                  +----------------------+     +---------------------------+
                                                 |       |         |
                                                 v       v         v
                                              agent/ repositories/ medical_records/
                                                 \       |         /
                                                  \      v        /
                                                   +-----------------------+
                                                   | Neo4j / Milvus / RAG |
                                                   +-----------------------+
                          |
                          v
                  +----------------------+
                  | JSON / NDJSON output |
                  +----------------------+
```

## Chi tiết theo file

### `main.py`

| Thành phần | Mô tả |
|---|---|
| `lifespan` | Context manager FastAPI: khi shutdown gọi `cleanup_roots_on_exit()` và xóa thư mục tạm (upload/extract) an toàn. |
| `create_app()` | Factory: `FastAPI` + CORS từ `settings.cors`, mount `/ui` (nếu `web_ui_dir` tồn tại), mount `/api/pill-images/static` từ `pill_image_dataset_dir()`. |
| `app` | Instance toàn cục + `include_router` cho `health`, `ollama`, `graphrag`, `agent`, và `medical_record_router` (prefix `/api/medical-record`). |
| Re-export | `QueryOut` từ `api.routes.graphrag` (tương thích import cũ); `check_rate_limit`, `get_client_ip` từ `dependencies`. |

### `dependencies.py`

| Thành phần | Mô tả |
|---|---|
| `_rate_limit_store` | Dict in-memory: IP → danh sách timestamp (monotonic) trong cửa sổ rate limit. |
| `get_settings_dep` | `Depends` → `get_settings()`. |
| `get_llm_backend_dep` | `Depends` → `get_llm_backend(backend="auto")`. |
| `get_knowledge_repo` | `Depends` → `get_default_repository()`. |
| `get_agent_service` | `Depends` → `AgentService(settings, llm_backend)`. |
| `SettingsDep`, `LLMBackendDep`, `KnowledgeRepoDep`, `AgentServiceDep` | Alias `Annotated[..., Depends(...)]` cho chữ ký route. |
| `get_client_ip(request)` | Lấy IP từ `X-Forwarded-For` hoặc `request.client.host`. |
| `check_rate_limit(request, settings)` | Nếu `max_per_window > 0`: dọn hit cũ, vượt ngưỡng → `HTTPException 429`. |

### `__init__.py`

- Package marker; `__all__` rỗng (docstring mô tả refactor từ `llm_pipeline/app.py`).

## Liên kết

- Route details: [`routes/README.md`](routes/README.md)
- README tổng: [`../README.md`](../README.md)
