# Tổ chức routes API

Thư mục `api/routes/` chia endpoint theo từng nhóm chức năng để người mới dễ tìm:

```
api/routes/
├── __init__.py          # Export các router
├── health.py            # Kiểm tra sống/chết và trạng thái hệ thống
├── ollama.py            # Proxy gọi Ollama
├── graphrag.py          # Hỏi đáp GraphRAG
└── agent.py             # Agent ReAct/legacy + stream
```

## Nguyên tắc thiết kế

1. **Một file, một nhóm nghiệp vụ**: giúp đọc code nhanh, không bị dồn logic vào một file lớn.
2. **Dependency Injection qua `Depends()`**: route chỉ nhận dependency đã chuẩn bị sẵn.
3. **Model hóa request/response bằng Pydantic**: API dễ đọc, tránh sai kiểu dữ liệu.
4. **Route mỏng**: route chỉ validate + gọi service/repository; business logic để ở tầng dưới.

## Mẫu router cơ bản

Mỗi file router thường theo mẫu này:

```python
from fastapi import APIRouter

router = APIRouter(
    prefix="/api/prefix",  # Có thể có hoặc không
    tags=["tag-name"]      # Nhóm hiển thị trên Swagger
)

@router.get("/endpoint")
async def endpoint_handler(
    dependency: DependencyType = Depends(),
) -> ResponseType:
    return result
```

## Tích hợp vào `api/main.py`

```python
from api.routes import health_router, ollama_router, graphrag_router, agent_router

app.include_router(health_router)
app.include_router(ollama_router)
app.include_router(graphrag_router)
app.include_router(agent_router)
```

## Tóm tắt endpoint theo router

| Router | Endpoint chính | Dùng khi nào |
|--------|----------------|--------------|
| `health` | `/`, `/health`, `/health/ready`, `/health/config`, `/health/performance` | Kiểm tra app có chạy không, phụ thuộc có sẵn sàng không |
| `ollama` | `/api/ollama/health`, `/api/ollama/chat` | Kiểm tra và gọi trực tiếp Ollama |
| `graphrag` | `/ask`, `/api/query` | Hỏi đáp qua tầng retrieval |
| `agent` | `/api/agent-query`, `/api/agent-query/stream`, `/api/langchain-graph-query`, `/api/langchain-graph-query/direct` | Gọi agent và luồng graph nâng cao |

## Chi tiết theo file

### `__init__.py`

- Export: `health_router`, `ollama_router`, `graphrag_router`, `agent_router`.

### `health.py` (`APIRouter`, tag `health`)

| Handler | Đường dẫn | Mô tả |
|---|---|---|
| `root` | `GET /` | Nếu có thư mục UI → `RedirectResponse` tới `/ui/`; không thì JSON gợi ý `/docs`, `/health`. |
| `health` | `GET /health` | `{"status": "ok"}`. |
| `health_ready` | `GET /health/ready` | Gọi `llm_pipeline.readiness.compute_readiness()` (Ollama, Neo4j, GraphRAG parquet, Milvus). |
| `health_config` | `GET /health/config` | Snapshot cấu hình an toàn: `LLM_BACKEND`, Ollama/OpenRouter, Neo4j enabled/URI. |
| `health_performance` | `GET /health/performance` | `core.cache.get_query_cache().stats()` + `core.connection_pool.get_driver_stats()`. |

### `graphrag.py` (tag `graphrag`)

| Model / handler | Mô tả |
|---|---|
| `QueryIn` | `message` 1–4000 ký tự. |
| `SourceOut`, `QueryOut` | `answer` + `sources` (title, link, source, score). |
| `ask` | `GET /ask?q=...` — `check_rate_limit`, `repo.query(q)` → chỉ `answer`. |
| `api_query` | `POST /api/query` — `repo.query` → `QueryOut` đầy đủ sources. |

### `ollama.py` (prefix `/api/ollama`, tag `ollama`)

| Model / handler | Mô tả |
|---|---|
| `OllamaChatIn` | `message`, `model?`, `temperature?`. |
| `OllamaChatOut` | `model`, `message` (nội dung trả lời). |
| `ollama_health` | `GET /health` — `OllamaBackend.is_available`, `list_models`, so khớp model env. |
| `ollama_chat` | `POST /chat` — `check_rate_limit`, `backend.chat(prompt, model, temperature)`. |

### `agent.py` (prefix `/api`, tag `agent`)

| Model / handler | Mô tả |
|---|---|
| `AgentQueryIn` | `message`, `strategy` auto\|graph, `use_langgraph`, `use_react`, `use_legacy_pipeline`, `backend` auto\|ollama\|openrouter. |
| `AgentQueryOut` | answer, strategy, plan, errors, sources, context previews, drug_images, medication_plan, reminders. |
| `api_agent_query` | `POST /agent-query` — chỉnh `settings.agent` theo body, tuỳ chọn tạo lại `AgentService` với backend khác; `service.execute(...)`. |
| `api_agent_query_stream` | `POST /agent-query/stream` — NDJSON từ `service.execute_stream`; từ chối nếu legacy hoặc `use_react=false`. |
| `LangChainGraphQueryIn/Out` | Message + answer, sources, `context_preview`. |
| `api_langchain_graph_query` | `POST /langchain-graph-query` — `RetrievalService.query_langchain_graph_with_sources` + preview từ `retrieve_langchain_graph_context`. |
| `api_langchain_graph_query_direct` | `POST /langchain-graph-query/direct` — `run_langchain_graphrag_query_direct` (không synthesis LLM). |

## Sơ đồ điều hướng theo router

```text
+--------------+
| HTTP Request |
+--------------+
       |
       v
+-------------------+
| Chọn router file  |
+-------------------+
  |      |      |      |
  v      v      v      v
health ollama graphrag agent
  |      |       |       |
  v      v       v       v
readiness Ollama repository agent_service / retrieval_service
                           |
                           v
                 agent/react | orchestrator | langchain_graphrag
```
