# Module Services

## Mục đích

`services/` là tầng nghiệp vụ trung gian:

- Nhận yêu cầu từ API.
- Chọn chiến lược thực thi phù hợp.
- Điều phối các module `agent/`, `repositories/`, `llm_pipeline/`.

## Thành phần

| File | Vai trò |
|---|---|
| `agent_service.py` | Điều phối chế độ ReAct / legacy / LangGraph |
| `retrieval_service.py` | Nghiệp vụ retrieval phục vụ query graph/langchain graph |

## Luồng chính

1. API gọi `AgentService.execute()` hoặc `execute_stream()`.
2. Service đọc config từ `core.settings`.
3. Service chọn mode thực thi.
4. Trả kết quả chuẩn hóa cho API layer.

## Chi tiết theo file

### `agent_service.py` — class `AgentService`

| Phương thức | Mô tả |
|---|---|
| `__init__(settings?, llm_backend?)` | Mặc định `get_settings()` và `get_llm_backend("auto")`. |
| `_create_llm_backend` | Sinh backend LLM từ env/settings. |
| `_should_use_legacy(force_legacy?)` | Legacy nếu `force_legacy`, hoặc `use_legacy_pipeline`, hoặc `use_react=false`. |
| `_should_use_langgraph(force_langgraph?)` | Bật khi flag và import `run_agent_demo_langgraph` thành công. |
| `execute(message, strategy, use_legacy, use_langgraph)` | Thứ tự: LangGraph (nếu bật) → legacy orchestrator → ReAct `run_sync`. |
| `execute_stream(message, strategy)` | Chỉ ReAct: `ReActAgent.run_stream`; từ chối legacy/LangGraph bằng `ValueError`. |
| `_run_react` | Khởi tạo `ReActAgent` với `react_max_iter` / `react_parse_retries`. |
| `_run_legacy` | `agent.orchestrator.run_agent_demo` + model/host/router Ollama từ settings. |
| `_run_langgraph` | `run_agent_demo_langgraph` (ImportError → `LLMBackendError`). |
| `is_available()` | `llm.is_available()` hoặc False nếu lỗi backend. |

### `retrieval_service.py` — class `RetrievalService`

| Phương thức | Mô tả |
|---|---|
| `__init__(repository?)` | Optional inject `KnowledgeRepository` (mặc định không dùng cho langchain graph). |
| `query(question, k)` | Truy knowledge qua `KnowledgeRepository` inject (không có repo → chuỗi mặc định); API hiện tại chủ yếu dùng `query_langchain_graph*`. |
| `query_langchain_graph(question)` | Wrapper `run_langchain_graphrag_query`. |
| `query_langchain_graph_with_sources(question)` | `run_langchain_graphrag_query_with_sources` → `(answer, sources)`. |

## Cần cải thiện

1. Tách interface service rõ hơn để test dễ mock.
2. Chuẩn hóa telemetry (latency từng bước, token usage, source counts).
3. Bổ sung fallback policy khi backend chính timeout.

## Sơ đồ luồng service

```text
+------------+      +--------------------------+
| api/routes | ---> | AgentService.execute(*)  |
+------------+      +--------------------------+
                            |
                            v
                 +-------------------------+
                 | chọn mode thực thi      |
                 +-------------------------+
                    |         |         |
                    v         v         v
                 ReAct     Legacy   LangGraph
                    \         |         /
                     \        v        /
                     +--------------------+
                     |   repositories/    |
                     +--------------------+
                              |
                              v
                    Neo4j / GraphRAG CLI
```

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Agent module: [`../agent/README.md`](../agent/README.md)
- Repositories: [`../repositories/README.md`](../repositories/README.md)
