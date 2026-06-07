# Phân hệ Tác tử Hội thoại Nhận thức (Cognitive Agent Module)
> **Trái tim tư duy lâm sàng** của hệ thống CDSS, chịu trách nhiệm tiếp nhận câu hỏi y tế, phân loại định tuyến, lập kế hoạch, truy vấn tri thức đồ thị Neo4j, và sinh câu trả lời đồng thuận chuẩn xác.

---

## 1. Tổng quan Kiến trúc Bộ phận

Thư mục `agent/` đóng vai trò là lõi xử lý lập luận nhận thức trong hệ thống CDSS. Để giảm thiểu độ trễ tối đa (từ ~15 giây xuống dưới 1.5 giây), luồng chạy LangGraph cồng kềnh và luồng Legacy cũ đã được **loại bỏ** trong quá trình tối ưu hóa. Hiện tại hệ thống vận hành duy nhất một luồng chẩn đoán tối ưu: **Hybrid Intent Router kết hợp ReAct Agent Core**.

### Sơ đồ Luồng Hoạt động Toàn trình (Bản vẽ tay bằng Ký tự ASCII)

```text
    +-----------------------------------------------------------+
    |                 [ Yêu cầu hỏi đáp Lâm sàng ]               |
    +-----------------------------------------------------------+
                                  |
                                  v
                    +---------------------------+
                    |    ROUTER CHIẾN LƯỢC      |
                    +---------------------------+
                      /                       \
        [Ý định direct_db]                 [Ý định RAG / Chẩn đoán]
                    /                           \
                   v                             v
        +---------------------+       +-----------------------+
        | Định tuyến nhanh 0ms|       | Vòng Lặp Lập Luận Lõi |
        | (So khớp chỉ số)    |       | ReAct Agent Core      |
        +---------------------+       +-----------------------+
                   |                             |
                   v                             v
                   +-------> [ HẠ TẦNG CDSS ] <--+
                             | - Neo4j / Graph-First Retrieval
                             | - Dược điển cục bộ (Pill store)
                             +------------------------+
                                         |
                                         v
                           +---------------------------+
                           |  Câu trả lời chuẩn y khoa  |
                           |  - Sơ đồ mạng lưới Vis.js |
                           |  - Ảnh minh họa thuốc     |
                           +---------------------------+
```

---

## 1.1 Chi tiết Luồng Lập luận ReAct Loop (Mạch Nhận thức chính)

Mạch ReAct (Reason + Action) vận hành dựa trên cơ chế lặp để kết nối LLM với các công cụ tra cứu tri thức thời gian thực. Dưới đây là mô tả chi tiết từng bước hoạt động bên trong `agent/react/agent.py`:

```text
     +-------------------------------------------------------------+
     | BƯỚC 1: Tiếp nhận câu hỏi & Dựng Context ban đầu            |
     | (System Prompt chuẩn hóa CDSS + Lịch sử Chat + Câu hỏi mới) |
     +-------------------------------------------------------------+
                                   |
                                   v
+--> +-------------------------------------------------------------+
|    | BƯỚC 2: Gọi LLM (Ollama/OpenRouter)                         |
|    | - Sinh luồng suy luận Thought dưới dạng Real-time Streaming |
|    +-------------------------------------------------------------+
|                                  |
|                                  v
|    +-------------------------------------------------------------+
|    | BƯỚC 3: Bộ phân tích cú pháp (ReActParser.parse)            |
|    +-------------------------------------------------------------+
|            /                     |                     \
|           /                     /                       \
|          / [Cú pháp Hợp lệ]    / [Phát sinh Lỗi]         \ [Có Câu trả lời]
|         v                     v                           v
|   +-------------+      +--------------+             +--------------+
|   | Phân tích   |      | BƯỚC 3.2:    |             | BƯỚC 3.3:    |
|   | Action gọi  |      | Kích hoạt    |             | Nhận diện    |
|   | Tool chuyên |      | LOOP-GUARD & |             | Final Answer |
|   | biệt        |      | RECOVERY     |             | y khoa       |
|   +-------------+      +--------------+             +--------------+
|          |                    |                            |
|          v                    v                            v
|   +-------------+      +--------------+             +--------------+
|   | BƯỚC 3.1:   |      | - Gửi lại    |             | KẾT THÚC     |
|   | Chạy công cụ|      |   lỗi về LLM |             | Trả kết quả  |
|   | - GraphRAG  |      |   để sửa đổi |             | hoàn chỉnh   |
|   | - Tra cứu   |      | - Giải cứu   |             | kèm minh     |
|   |   ảnh thuốc |      |   văn bản thô|             | chứng (XAI)  |
|   +-------------+      +--------------+             +--------------+
|          |                    |
|          v                    |
|   +-------------+             |
|   | Bọc kết quả |             |
|   | dạng        | <-----------+
|   | Observation |
|   +-------------+
|          |
|          v
+---- [Lặp lại vòng tiếp theo] (Tối đa AGENT_REACT_MAX_ITER)
```

### Giải thích các bước vận hành lâm sàng chi tiết:

1. **Thiết lập Nhận thức ban đầu (Bước 1)**:
   Hệ thống nạp vào bộ nhớ LLM một **System Prompt** nghiêm ngặt chỉ dẫn LLM đóng vai trò là Chuyên gia CDSS. LLM buộc phải tuân theo cấu trúc suy luận:
   `Thought` (Mạch suy nghĩ lâm sàng của bác sĩ) -> `Action` (Hành động gọi công cụ để kiểm chứng) -> `Action Input` (Tham số truyền vào công cụ) -> `Observation` (Dữ liệu thực tế thu về từ công cụ) -> Lặp lại -> `Final Answer` (Khuyến nghị cuối cùng gửi bệnh nhân).

2. **Gọi Lập luận & Streaming (Bước 2 & 3)**:
   LLM bắt đầu viết luồng suy nghĩ. Hệ thống trích xuất phần suy nghĩ y khoa này và phát trực tiếp lên màn hình của nhân viên y tế thông qua sự kiện `reasoning_delta` để bác sĩ theo dõi được luồng tư duy.

3. **Phân nhánh xử lý (Bước 3.1, 3.2, 3.3)**:
   - **Nhánh gọi công cụ (Step 3.1)**: Nếu LLM viết `Action: graphrag_query`, hệ thống sẽ tạm dừng LLM, lấy giá trị của `Action Input` để chạy truy vấn thực tế vào cơ sở dữ liệu Neo4j. Kết quả trả về từ đồ thị sẽ được định dạng lại thành một khối dữ liệu thuần túy dưới thẻ `Observation: ...` và nối vào lịch sử trò chuyện để chuẩn bị cho lượt suy nghĩ tiếp theo.
   - **Nhánh giải cứu lỗi (Step 3.2 - Loop-Guard)**: Nếu LLM viết sai định dạng (ví dụ: dùng sai tên công cụ hoặc bỏ quên thẻ đóng), bộ **ReActParser** sẽ phát hiện. Hệ thống sẽ tự động gửi lại thông báo lỗi chi tiết cho LLM để yêu cầu nó tự sửa lỗi (tối đa `AGENT_REACT_PARSE_RETRIES` lần). Nếu vượt quá số lần sửa lỗi hoặc vòng lặp chạm ngưỡng `AGENT_REACT_MAX_ITER`, bộ cứu hộ sẽ tự động gom các thông tin đã tra cứu được để tổng hợp câu trả lời cứu hộ an toàn trong thời gian dưới 3 giây.
   - **Nhánh hoàn thành (Step 3.3)**: Khi LLM đã thu thập đủ dữ liệu y khoa chuẩn xác, nó sẽ viết `Final Answer: ...`. Vòng lặp dừng lại.

---

## 2. Chi tiết Danh mục Thành phần Lõi

### A. Tác tử ReAct (Reason + Action) Loop (`react/`)
Đây là công nghệ trung tâm của dự án, cho phép mô hình cục bộ (như Llama-3.1-8B) suy nghĩ từng bước trước khi đưa ra quyết định:
- **`react/agent.py`**: Lớp lõi `ReActAgent` điều phối vòng lặp suy nghĩ và tương tác công cụ, hỗ trợ hoàn chỉnh cả phương thức đồng bộ `run_sync` và streaming thời gian thực `run_stream` qua SSE.
- **`react/parser.py`**: Trình phân tích cú pháp nghiêm ngặt bóc tách `Thought`, `Action`, `Action Input` và `Final Answer` từ văn bản sinh ra bởi LLM.
- **`react/prompts.py`**: Hệ thống prompts học thuật định hướng bằng tiếng Việt, thiết lập ngữ cảnh chuyên gia y khoa CDSS và cơ chế hướng dẫn định dạng.
- **`react/tools.py`**: Lớp trung gian thực thi công cụ đặc hiệu của ReAct (truy vấn đồ thị tri thức, tìm kiếm thuốc).

### B. Thành phần bổ trợ (Legacy / Experimental)
- **`__main__.py`**: Điểm bắt đầu (CLI entry point) cho phép chạy thử nghiệm và đánh giá chất lượng Agent từ Command Line.
- **`orchestrator.py` (Legacy)**: Luồng xử lý tuần tự truyền thống (đã nghỉ hưu trong uvicorn server).
- **`langgraph_app.py` (Legacy)**: State machine sử dụng LangGraph thiết kế luồng tuần tự (đã nghỉ hưu trong uvicorn server).
- **`router.py`**: Hệ thống phân loại câu hỏi (Social conversational vs. Medical RAG) sử dụng kỹ thuật Heuristics kết hợp LLM Prompting kiểu NeMo Guardrails để chuyển hướng yêu cầu chính xác.
- **`retrieval_confidence.py`**: Thuật toán đánh giá độ tin cậy của ngữ cảnh RAG (`Level: cao/trung/thap`) dựa trên mật độ ký tự, điểm số truy xuất cao nhất và tính sẵn có của tài liệu nguồn.
- **`medication_tools.py`**: Công cụ trích xuất thực thể dược học lâm sàng tự động từ văn bản truy xuất và lập lịch nhắc uống thuốc mẫu.

---

## 3. Bản đồ chi tiết các API & Hàm nghiệp vụ cốt lõi

### Lớp Lập luận ReAct (`react/agent.py`)
- `run_stream(question, ...)`: Phát ra các sự kiện SSE (`reasoning_delta`, `tool`, `tool_done`, `answer_delta`) giúp UI hiển thị sinh động luồng tư duy.
- `_forced_finalize_answer(...)`: Cơ chế Loop-Guard kích hoạt khi phát hiện Agent bị lặp vô hạn hoặc vượt quá số vòng lặp an toàn (`AGENT_REACT_MAX_ITER`). Nó sẽ tự động tóm tắt nhanh từ ngữ cảnh đồ thị hiện tại để cứu hộ câu trả lời.

### Bộ cứu hộ cú pháp (`react/parser.py`)
- `parse(text)`: Sử dụng biểu thức chính quy (Regex) và phân tích chuỗi để bóc tách hành động của tác tử.
- `extract_fallback_answer(...)`: Khi LLM sinh lỗi định dạng nhưng đã có câu trả lời bên trong, bộ lọc này sẽ giải cứu văn bản thô để tránh lỗi crash hệ thống.

---

## 4. Biến số Môi trường Vận hành Chính

| Biến số | Kiểu dữ liệu | Giá trị mặc định | Vai trò |
|---|---|---|---|
| `AGENT_USE_REACT` | `bool` | `true` | Kích hoạt vòng lặp nhận thức ReAct |
| `AGENT_REACT_MAX_ITER` | `int` | `5` | Giới hạn vòng lặp ReAct tối đa để tránh lặp vô hạn |
| `AGENT_REACT_PARSE_RETRIES`| `int` | `2` | Số lần thử lại nhắc định dạng nếu LLM sinh cú pháp lỗi |
| `OLLAMA_MODEL` | `str` | `llama3.1:8b` | Mô hình ngôn ngữ nền tảng xử lý lập luận |

---

## 5. Hướng phát triển nâng cấp (Roadmap)
1. **Pydantic Structured Output**: Ép buộc LLM trả về cấu hình JSON chính xác cho Tool Calls thay vì phân tích Markdown Regex thô.
2. **Multi-Agent Orchestration**: Tách Agent nhận thức đơn lẻ này thành một nhóm 4 Agent chuyên khoa bằng LangGraph phối hợp bầu chọn.
3. **Phân tách LLM**: Dùng mô hình siêu nhỏ (như Qwen-2.5-1.5B) để làm tác tử Router định tuyến tốc độ cao và giữ Llama-3.1-8B làm tác tử chính để lập luận sâu.

---
*Xem thêm tài liệu tổng thể tại [README tổng](../README.md).*
