# Agent Module

## Mục đích

Thư mục `agent/` chứa toàn bộ logic điều phối hỏi đáp thông minh:

- Chế độ mặc định: ReAct agent.
- Chế độ tương thích ngược: legacy orchestrator.
- Chế độ legacy + LangGraph.
- Tooling bổ trợ như router chiến lược và tính điểm tin cậy retrieval.

## Thành phần chính

| File | Vai trò |
|---|---|
| `__main__.py` | Entry CLI cho `python -m agent` |
| `orchestrator.py` | Luồng orchestrator cũ |
| `langgraph_app.py` | Luồng LangGraph cho legacy mode |
| `router.py` | Chọn strategy `auto`/`graph` |
| `tools.py` | Tool layer cho agent ngoài ReAct core |
| `retrieval_confidence.py` | Tính confidence cho context retrieval |
| `medication_tools.py` | Tool nghiệp vụ liên quan thuốc |

### `react/` submodule

| File | Vai trò |
|---|---|
| `react/agent.py` | Lõi `ReActAgent`, có `run_sync()` và `run_stream()` |
| `react/parser.py` | Parse format action/final answer của LLM |
| `react/tools.py` | Tool execution cho ReAct |
| `react/prompts.py` | Prompt templates cho ReAct |

## Chi tiết hàm / lớp theo từng file

### `__main__.py`

| Hàm | Mô tả ngắn |
|---|---|
| `main()` | Định nghĩa CLI (`argparse`), phân nhánh `--legacy` + `--langgraph` → `run_agent_demo_langgraph` / `run_agent_demo`, mặc định → `run_react_agent`; in JSON (`--json`) hoặc Plan / Errors / Answer. |

### `__init__.py` (gói `agent`)

- Chỉ khai báo `__version__` và docstring tổng quan; không có hàm nghiệp vụ.

### `orchestrator.py`

| Hàm / lớp | Mô tả ngắn |
|---|---|
| `run_agent_demo(...)` | Pipeline legacy: `plan_retrieval` → (tuỳ plan) `tool_graphrag_query` → nhánh medication (`parse_medication_intent`, `extract_drug_info_from_collection_context`, …) → `merge_context_blocks` + `answer_with_ollama`; trả dict trace (plan, context preview/full, sources, drug_images, medication_plan, reminders, answer, errors). |

### `langgraph_app.py`

| Hàm / lớp | Mô tả ngắn |
|---|---|
| `AgentState` | `TypedDict` state cho graph (question, plan, graph_text, hits, errors, …). |
| `_err(state, msg)` | Gộp thêm một dòng lỗi vào `errors`. |
| `build_router_node()` | Factory trả node gọi `plan_retrieval`, ghi `plan` vào state. |
| `build_graphrag_node()` | Factory node: nếu `use_graphrag` thì `tool_graphrag_query`, không thì rỗng; lỗi GraphRAG ghi vào `errors`. |
| `build_synthesize_node()` | Factory node: xử lý medication giống orchestrator, `merge_context_blocks`, `answer_with_ollama`, cập nhật `plan.llm_grounded`. |
| `build_medical_agent_graph()` | `StateGraph` tuyến tính: START → router → graphrag → synthesize → END. |
| `run_agent_demo_langgraph(...)` | `graph.invoke(initial_state)` sau đó chuẩn hoá output giống `run_agent_demo` (preview, sources, …). |

### `router.py`

| Hàm / lớp / hằng | Mô tả ngắn |
|---|---|
| `RouterBranch` | Dataclass: `name` + `description` cho prompt router. |
| `ROUTER_BRANCHES` | Danh sách nhánh `social` / `graphrag` (mô tả cho LLM). |
| `RetrievalPlan` | Kết quả định tuyến: `use_graphrag`, `reason`, `router_route`, `next_pipeline`. |
| `DEFAULT_ROUTER_MODEL`, `DEFAULT_ROUTER_RETRIES`, `ALLOWED_ROUTES` | Hằng cấu hình / tập nhánh hợp lệ. |
| `_router_heuristics_enabled()` | Đọc `AGENT_ROUTER_HEURISTICS` có bật heuristic không. |
| `_next_pipeline(route)` | Map route → `"social_llm"` hoặc `"rag_llm"`. |
| `_branch_catalog_text()`, `_branch_names_csv()` | Text mô tả nhánh và CSV tên nhánh cho prompt. |
| `is_obvious_pure_social(question)` | Regex chào hỏi / cảm ơn ngắn → coi là social. |
| `is_meta_conversational_opener(question)` | Câu xin phép hỏi chưa có hint y khoa → social. |
| `_parse_branch_name_only`, `_parse_router_json`, `_parse_route_from_llm_output` | Parse output Ollama: một dòng tên nhánh hoặc JSON `route`/`reason`. |
| `_build_router_prompt_neomo_style(question)` | Prompt user message kiểu router NeMo (chỉ trả tên nhánh). |
| `_llm_route_plan(...)` | POST `/api/chat` Ollama, retry parse, trả `RetrievalPlan`. |
| `plan_retrieval(...)` | API công khai: `strategy=graph` → luôn graphrag; `auto` → heuristic (nếu bật) rồi LLM router; lỗi router → fallback graphrag. |

### `tools.py`

| Hàm | Mô tả ngắn |
|---|---|
| `expand_query_with_llm(question, num_variations)` | Sinh biến thể query qua LLM + JSON array; câu dài (>10 từ) trả chỉ `[question]`; lỗi → fallback một query. |
| `tool_graphrag_query(question, ...)` | Gọi `run_graphrag_query`; có thể merge nhiều biến thể (`use_expansion=True`) và gộp text dedupe. |
| `tool_pill_image_lookup(query)` | `lookup_pill_images` + `format_pill_image_observation` → chuỗi Observation. |
| `pill_image_lookup_with_urls(query, limit)` | Cùng observation + list URL ảnh. |
| `try_auto_pill_images_for_question(question)` | Chỉ tra ảnh khi `resolve_pill_lookup_query` khớp alias thuốc. |
| `merge_context_blocks(graphrag_text)` | Bọc block GraphRAG cho prompt RAG hoặc placeholder không có retrieval. |
| `merge_retrieval_hits(existing, new)` | Gộp hit theo (title, source), giữ score cao hơn. |
| `augment_sources_for_ui(hits, graph_text)` | Nếu có context nhưng không có hit → thêm một dòng nguồn placeholder cho UI. |

### `retrieval_confidence.py`

| Hàm / kiểu | Mô tả ngắn |
|---|---|
| `Level` | Literal `"cao"` / `"trung"` / `"thap"`. |
| `compute_retrieval_confidence(sources, graph_text)` | Heuristic độ tin cậy: độ dài context, max score nguồn, số nguồn có điểm, có URL hay không → dict `level`, `label_vi`, metrics. |

### `medication_tools.py`

| Hàm / lớp | Mô tả ngắn |
|---|---|
| `MedicationIntent` | Dataclass: cờ drug_info/plan/reminders + `drug_name`, `doses_per_day`, `days`. |
| `parse_medication_intent(question)` | Keyword + regex liều/ngày + `_extract_drug_name` → `MedicationIntent`. |
| `_extract_drug_name(question)` | Trích tên thuốc (trích dẫn, pattern sau "thuốc", whitelist tên phổ biến, token Latin ngắn). |
| `lookup_drug_info_and_images(...)` | Stub deprecated; báo lỗi khuyến nghị dùng extraction từ context. |
| `extract_drug_info_from_collection_context(drug_name, graphrag_text)` | Tóm tắt + URL + ảnh từ text GraphRAG (`_extract_all_urls`, `_extract_image_urls`). |
| `_extract_image_urls`, `_extract_all_urls` | Regex URL / lọc URL ảnh. |
| `build_medication_plan(...)` | Lịch uống mẫu đều trong khoảng thức–ngủ (`_parse_hhmm`). |
| `build_reminder_events(plan_rows)` | Map từng dòng plan → `{title, datetime_local, message}`. |
| `render_medication_context(info, plan_rows, reminders)` | Chuỗi context ghép các block cho LLM. |
| `_parse_hhmm(value, default)` | Parse `"HH:MM"`. |

### `react/agent.py`

| Hàm / lớp | Mô tả ngắn |
|---|---|
| `_want_agent_terminal_log()`, `_recovery_enabled()` | Đọc settings: trace và có cho phép recovery parse không. |
| `_chunk_stream_answer(answer)` | Cắt answer thành chunk nhỏ cho stream. |
| `_append_answer_source_note(...)` | Thêm dòng "Nguồn trả lời: RAG / LLM trực tiếp". |
| `_forced_finalize_answer(question, graph_context)` | Khi model lặp tool: tóm tắt từ context hoặc báo thiếu dữ liệu. |
| `_build_result_bundle(...)` | Dict chuẩn cho API: answer, plan steps, previews, sources, `retrieval_confidence`. |
| `ReActAgent` | Vòng lặp ReAct: `_create_initial_messages`, `_execute_tool`, `run_sync`, `run_stream` (recovery, loop guard trùng `graphrag_query`, merge hits/ảnh). |
| `run_react_agent(...)`, `run_react_agent_event_stream(...)` | Khởi tạo `OllamaBackend` + `ReActAgent`; wrapper đồng bộ / stream. |

### `react/parser.py`

| Hàm / lớp | Mô tả ngắn |
|---|---|
| `ReActParseResult` | Dataclass: `kind` action/finish/error + `action`, `input_text`, `answer`, `error_message`. |
| `TOOL_ALIASES`, `ALLOWED_TOOLS`, các `re.compile` | Alias tên tool và pattern parse. |
| `ReActParser._normalize_markdown`, `_strip_tool_noise` | Chuẩn hoá `**Thought**` và tên tool. |
| `ReActParser.parse(text)` | Trả action + input hoặc final answer hoặc lỗi (ưu tiên không trùng Action + Final Answer). |
| `ReActParser.extract_fallback_answer(text)` | Recovery: lấy phần sau `Final Answer:` hoặc toàn bộ text nếu không có action graphrag. |

### `react/tools.py`

| Hàm | Mô tả ngắn |
|---|---|
| `_get_repo()` | Lazy singleton `get_knowledge_repository("auto")`. |
| `set_repository(repo)` | Inject repo (test). |
| `run_graphrag_tool(action_input, original_question, use_expansion)` | Query repo: có expansion biến thể ngắn; merge query gốc + action input khi khác nhau. |
| `run_pill_image_tool(action_input)` | `pill_image_lookup_with_urls`. |
| `merge_pill_observation(question, base_observation, current_image_urls)` | Gộp observation ảnh tự nhận từ câu hỏi + URL tích luỹ. |

### `react/prompts.py`

| Hàm | Mô tả ngắn |
|---|---|
| `get_react_system_prompt()` | Prompt tiếng Việt: mô tả `graphrag_query` / `pill_image_lookup`, quy tắc ReAct và Final Answer sau Observation. |
| `get_parse_retry_prompt(error_message)` | User message nhắc sửa format sau lỗi parse. |
| `create_recovery_synthetic_message(question)` | Assistant giả lập Action `graphrag_query` + Action Input = câu hỏi (recovery lượt 1). |

### `react/__init__.py`

| Export | |
|---|---|
| `ReActAgent`, `ReActParser`, `ReActParseResult`, `run_react_agent`, `run_react_agent_event_stream` | Re-export từ `agent.react.agent` / `parser`. |

## Cách chạy nhanh

```bash
# ReAct mặc định
python -m agent --question "Triệu chứng của cúm là gì?" --json

# Legacy
python -m agent --legacy --question "Tư vấn phòng tăng huyết áp"

# LangGraph chỉ áp dụng với legacy
python -m agent --legacy --langgraph --question "Tương tác thuốc A và B"
```

## Biến cấu hình liên quan

- `AGENT_USE_REACT`
- `AGENT_USE_LEGACY_PIPELINE`
- `AGENT_USE_LANGGRAPH`
- `AGENT_REACT_MAX_ITER`
- `AGENT_REACT_PARSE_RETRIES`
- `AGENT_TRACE`
- `OLLAMA_HOST`
- `OLLAMA_MODEL`

## Lưu ý kỹ thuật

- Streaming (`/api/agent-query/stream`) chỉ hỗ trợ ReAct.
- `--langgraph` không có tác dụng nếu không bật `--legacy`.
- Agent phụ thuộc mạnh vào chất lượng retrieval từ `repositories/`.

## Sơ đồ luồng Agent (ReAct mặc định)

```text
+---------------------+
| Câu hỏi người dùng  |
+---------------------+
          |
          v
 +------------------------------+
 | ReActAgent.run_sync/stream   |
 +------------------------------+
          |
          v
 +------------------------------+
 | ReActParser.parse            |
 +------------------------------+
          |
          v
   Action ? hay Final Answer ?
      |                   |
      | Action            | Final
      v                   v
 run_graphrag_tool   answer + sources + confidence
 run_pill_image_tool
      |        |
      v        v
repositories  pill_image_store
      |
      v
Observation -> quay lại vòng ReAct
```

## Cần cải thiện

1. Tách rõ API model cho tool-call và final-answer để giảm parse retry.
2. Thêm structured output ràng buộc schema (Pydantic parsing trực tiếp).
3. Bổ sung benchmark đa chiến lược (ReAct vs legacy vs langgraph) theo latency + groundedness.

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Service điều phối: [`../services/README.md`](../services/README.md)
- Repository tri thức: [`../repositories/README.md`](../repositories/README.md)
