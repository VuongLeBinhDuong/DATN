# Module Core

## Mục đích

`core/` cung cấp hạ tầng dùng chung:

- Nạp cấu hình tập trung.
- Lớp trừu tượng backend LLM.
- Cache và connection pooling.

## Thành phần

| File | Vai trò |
|---|---|
| `settings.py` | Cấu hình toàn hệ thống bằng Pydantic Settings |
| `llm_backends.py` | Interface và implementation backend (Ollama/OpenRouter) |
| `cache.py` | Query cache và thống kê hit/miss |
| `connection_pool.py` | Theo dõi/điều phối kết nối driver |

## Nguyên tắc cấu hình

- Ưu tiên env variables.
- Local có thể nạp thêm từ `.env` root và `config/.env`.
- Khi chạy trong Docker (`RUNNING_IN_DOCKER=1`) bỏ qua load `.env` cục bộ để tránh conflict.

## Cách dùng

```python
from core.settings import get_settings

settings = get_settings()
print(settings.ollama.host)
print(settings.neo4j.enabled)
```

## Chi tiết theo file

### `settings.py`

| Thành phần | Mô tả |
|---|---|
| `_repo_root()` | Đường dẫn gốc repo để resolve file config. |
| `OllamaSettings`, `OpenRouterSettings`, `Neo4jSettings`, `RateLimitSettings`, `AgentSettings`, `VectorStoreSettings`, `CorsSettings` | Nhóm cấu hình Pydantic (env prefix / field validators tuỳ mục). |
| `Settings` | Gộp toàn bộ; `web_ui_dir`, `expose_retrieval_debug`, v.v. |
| `get_settings()` | Singleton cached `@lru_cache`. |
| `_is_running_in_docker()`, `_load_dotenv_files()` | Docker: tránh `.env` local; load `.env` root + `config/.env`. |

### `llm_backends.py`

| Thành phần | Mô tả |
|---|---|
| `get_synthesis_backend()` | Chọn backend synthesis mặc định (`ollama` / `openrouter`). |
| `LLMBackend` (ABC) | `chat`, `chat_stream`, `is_available`, `list_models` (tuỳ implementation). |
| `LLMBackendError` | Lỗi HTTP/status từ backend. |
| `OllamaBackend` | REST Ollama: chat sync/stream, kiểm tra model. |
| `OpenRouterBackend` | REST OpenRouter tương tự. |
| `get_llm_backend(backend="auto"|"ollama"|"openrouter")` | Factory theo env / tham số. |

### `cache.py`

| Thành phần | Mô tả |
|---|---|
| `SimpleCache` | Cache query (TTL/size tuỳ cài đặt), `stats()` hit/miss. |
| `get_query_cache()`, `clear_query_cache()` | Singleton và xoá cache. |

### `connection_pool.py`

| Hàm | Mô tả |
|---|---|
| `_make_driver_key`, `_normalize_bolt_uri` | Key pool + chuẩn hoá bolt URI. |
| `get_neo4j_driver(...)` | Neo4j driver có pooling dùng lại theo URI/user/db. |
| `close_all_drivers()`, `get_driver_stats()` | Đóng pool / metrics cho `/health/performance`. |
| `configure_pool_from_settings()` | Áp limits từ `Settings`. |

## Cần cải thiện

1. Thêm command `validate-config` để fail-fast trước khi chạy app.
2. Bổ sung profile config theo môi trường (`dev`, `test`, `prod`).
3. Thêm circuit-breaker và retry policy cho backend LLM.

## Sơ đồ hạ tầng lõi

```text
+------------------------------+
| ENV + .env + config/*.json   |
+------------------------------+
               |
               v
      +------------------+
      | get_settings()   |
      +------------------+
        |      |      |
        v      v      v
    rate   llm cfg   neo4j cfg

api/services/agent
        |
        v
+----------------------+
| get_llm_backend()    |
+----------------------+
    |              |
    v              v
 OllamaBackend  OpenRouterBackend

api/services/agent --> SimpleCache
api/services/agent --> get_neo4j_driver
```

## Liên kết

- README tổng: [`../README.md`](../README.md)
- API dependency injection: [`../api/README.md`](../api/README.md)
