# Module LLM Pipeline

## Mục đích

`llm_pipeline/` chứa các thành phần legacy và adapter retrieval/LLM còn được tái sử dụng ở nhiều luồng.

## Thành phần

| File | Vai trò |
|---|---|
| `chat.py` | Chat helper cơ bản |
| `llm_chat.py` | Lớp gọi LLM |
| `rag_llm.py` | Kết hợp context retrieval và sinh câu trả lời |
| `graphrag_query.py` | Truy vấn graph rag |
| `neo4j_graphrag.py` | Truy vấn graph trên Neo4j |
| `langchain_graphrag.py` | Truy vấn nhánh langchain graph |
| `parquet_to_neo4j.py` | Import dữ liệu parquet vào Neo4j |
| `readiness.py` | Kiểm tra readiness của dependencies |
| `terminal_logging.py` | Logging utility |

## Khi nào nên dùng

- Dùng cho các script vận hành và đường tương thích ngược.
- Với code mới, ưu tiên đi qua `services/` + `repositories/` trước, chỉ gọi trực tiếp khi thực sự cần.

## Nếu bạn chỉ cần hiểu "GraphRAG + LLM chạy qua file nào"

### Luồng 1 (hay gặp nhất trong app hiện tại): API/Agent -> `repositories` -> Neo4j GraphRAG

Đây là luồng mặc định khi bạn hỏi qua API agent hoặc API graphrag:

1. Route nhận request:
   - `api/routes/agent.py` hoặc `api/routes/graphrag.py`
2. Route gọi service:
   - `services/agent_service.py` (đối với agent)
3. Service/agent gọi tầng repository:
   - `repositories/factory.py` -> chọn `Neo4jRepository` trong `repositories/neo4j_repo.py` (nếu Neo4j sẵn sàng)
4. Repository gọi hàm truy vấn context:
   - `llm_pipeline/neo4j_graphrag.py` -> `retrieve_graph_context_with_sources(...)`
5. Kết quả trả về:
   - `context` + `sources` (điểm fulltext, neighbors, community summary)
6. Nếu cần LLM tổng hợp:
   - thường do agent/service xử lý tiếp (ReAct hoặc legacy)

Nói ngắn gọn: **request thật của app thường đi qua `repositories/neo4j_repo.py` trước, rồi mới vào `llm_pipeline/neo4j_graphrag.py`.**

### Luồng 2 (legacy rõ ràng nhất "GraphRAG + Ollama synthesis" trong folder này)

Khi chạy legacy orchestrator (`agent/orchestrator.py`):

1. `agent/orchestrator.py` gọi `agent/tools.py` -> `tool_graphrag_query(...)`
2. `tool_graphrag_query(...)` gọi:
   - `llm_pipeline/graphrag_query.py` -> `run_graphrag_query(...)`
3. Trong `run_graphrag_query(...)`:
   - nếu Neo4j bật (`config/neo4j.json`) -> dùng `llm_pipeline/neo4j_graphrag.py`
   - nếu không -> fallback GraphRAG CLI
4. Sau khi có context, orchestrator gọi:
   - `llm_pipeline/rag_llm.py` -> `answer_with_ollama(...)`
5. `answer_with_ollama(...)` đọc prompt từ:
   - `prompts/*.txt` (qua `_read_prompt_file`) rồi POST tới Ollama `/api/chat`

Nói ngắn gọn: **"GraphRAG + LLM" theo kiểu legacy = `graphrag_query.py` (lấy context) + `rag_llm.py` (tổng hợp câu trả lời).**

### Luồng 3 (LangChain GraphRAG)

1. `api/routes/agent.py` endpoint `/api/langchain-graph-query`
2. gọi `services/retrieval_service.py`
3. gọi `llm_pipeline/langchain_graphrag.py`:
   - `run_langchain_graphrag_query_with_sources(...)` hoặc `run_langchain_graphrag_query(...)`
4. trong file này:
   - `retrieve_langchain_graph_context(...)` lấy context từ graph
   - `synthesize_langchain_answer(...)` gọi LLM để trả lời cuối

## Bảng "muốn làm gì thì vào file nào"

| Bạn muốn chỉnh gì | File nên mở đầu tiên |
|---|---|
| Cách truy context từ Neo4j GraphRAG | `llm_pipeline/neo4j_graphrag.py` |
| Cách fallback sang GraphRAG CLI | `llm_pipeline/graphrag_query.py` |
| Cách LLM tổng hợp từ context | `llm_pipeline/rag_llm.py` |
| Prompt dùng khi tổng hợp | `prompts/agent_merged_context_prompt.txt`, `prompts/grounded_rag_prompt.txt` |
| Luồng LangChain graph | `llm_pipeline/langchain_graphrag.py` |
| Điểm route gọi vào luồng trên | `api/routes/agent.py`, `api/routes/graphrag.py` |
| Điểm service điều phối | `services/agent_service.py`, `services/retrieval_service.py` |

## Chi tiết theo file (API công khai chính)

### `graphrag_query.py`

| Hàm | Mô tả |
|---|---|
| `run_graphrag_query(question, retrieval_query?)` | Đầu vào CLI GraphRAG; có thể tách `retrieval_query`. |
| `run_graphrag_query_with_sources(...)` | Trả text + structured sources cho UI/debug. |

### `neo4j_graphrag.py`

| Hàm | Mô tả |
|---|---|
| `default_neo4j_config_path`, `load_neo4j_config`, `neo4j_enabled` | Đường dẫn và bật/tắt Neo4j. |
| `retrieve_graph_context_with_sources(question, ...)` | Fulltext + neighbor + citations. |
| `retrieve_graph_context`, `synthesize_graph_answer` | Context thuần / gọi LLM tổng hợp. |

### `rag_llm.py`

| Hàm | Mô tả |
|---|---|
| `answer_extractively` | Trả lời rút trích không LLM đầy đủ (helper). |
| `answer_with_ollama(question, merged_context, ..., grounded, prompt_basename)` | Prompt từ `prompts/` + Ollama (dùng legacy orchestrator). |

### `llm_chat.py` / `chat.py`

| Hàm | Mô tả |
|---|---|
| `synthesis_backend`, `chat_ollama`, `chat_openrouter` | Chat trực tiếp một turn. |
| `chat.main` | Entry CLI nhỏ (nếu dùng). |

### `langchain_graphrag.py`

| Hàm (chọn lọc) | Mô tả |
|---|---|
| `retrieve_langchain_graph_context` | Truy Neo4j graph LangChain entity + vector context. |
| `synthesize_langchain_answer` | LLM trên context. |
| `run_langchain_graphrag_query` | Query + synthesis một hàm. |
| `run_langchain_graphrag_query_direct` | Raw context + sources (endpoint direct). |
| `run_langchain_graphrag_query_with_sources` | Trả `(answer, sources)` cho API/service. |

### `readiness.py`

| Hàm | Mô tả |
|---|---|
| `_ollama_ready`, `_neo4j_ready`, `_graphrag_parquet_ready` | Từng dependency. |
| `compute_readiness()` | Gộp dict trạng thái cho `/health/ready`. |

### `parquet_to_neo4j.py`

| Hàm | Mô tả |
|---|---|
| `sync_parquet_to_neo4j(...)` | Đồng bộ entity parquet → Neo4j (index, batch). |
| `main()` | CLI import. |

### `terminal_logging.py`

| Hàm | Mô tả |
|---|---|
| `configure_package_terminal_logging()` | Cấu hình logging terminal cho package. |

## Cần cải thiện

1. Tách rõ phần legacy và phần active để tránh nhầm lẫn.
2. Chuẩn hóa naming và hạn chế duplicate logic với `repositories/`.
3. Bổ sung test contract cho các hàm được API route sử dụng trực tiếp.

## Sơ đồ luồng `llm_pipeline`

```text
+----------------------------+
| Input từ services / agent  |
+----------------------------+
      |          |          |
      v          v          v
graphrag_query neo4j_graphrag langchain_graphrag
      \          |          /
       \         |         /
        +----------------------+
        |   graph context      |
        +----------------------+
                  |
                  v
      rag_llm.answer_with_ollama
                  |
                  v
            Ollama/OpenRouter

readiness.py -------------> /health/ready
parquet_to_neo4j.py ------> Neo4j
```

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Repositories: [`../repositories/README.md`](../repositories/README.md)
