# Phân hệ Dịch vụ Nghiệp vụ Trung gian (Business Services Layer)
> **Bộ não điều hành nghiệp vụ** nằm ở tầng trung gian của hệ thống CDSS, chịu trách nhiệm nhận yêu cầu xử lý từ API, phân tích cấu hình hệ thống, quyết định chiến lược xử lý tối ưu và điều phối các cấu phần lâm sàng chuyên biệt.

---

## 1. Bản đồ luồng điều phối nghiệp vụ

Tầng **Services Layer** đóng vai trò là cầu nối liên kết lỏng (loose coupling) giữa lớp giao diện API và các phân hệ xử lý hạ tầng/thuật toán phức tạp:

```text
     +-------------------------------------------------------------+
     |                 [ API Presentation Layer ]                  |
     +-------------------------------------------------------------+
                                   |
                                   | Gọi thực thi API
                                   v
     +-------------------------------------------------------------+
     |                [ AgentService.execute(*) ]                  |
     +-------------------------------------------------------------+
                                   |
                                   | Đọc cấu hình hệ thống & Env
                                   v
                    +-----------------------------+
                    |    LỰA CHỌN CHIẾN LƯỢC      |
                    +-----------------------------+
                      /             |             \
         [LangGraph] /              | [ReAct]      \ [Legacy]
                    /               |               \
                   v                v                v
        +------------------+  +-----------+  +-------------------+
        | langgraph_app.py |  | ReAct     |  | orchestrator.py   |
        | (State Machine)  |  | Agent     |  | (Legacy Pipeline) |
        +------------------+  +-----------+  +-------------------+
                 \                  |                  /
                  \                 v                 /
                   +-------> [ TRUY XUẤT ] <---------+
                             | RetrievalService /    |
                             | Repositories Layer    |
                             +-----------------------+
                                        |
                                        v
                             +-----------------------+
                             |   [ Neo4j & GraphRAG ]|
                             +-----------------------+
```

---

## 2. Chi tiết các Dịch vụ Nghiệp vụ cốt lõi

### A. Dịch vụ Điều phối Tác tử chuyên nghiệp (`AgentService`)
Chịu trách nhiệm khởi tạo trạng thái tác tử lâm sàng, điều phối các backend mô hình ngôn ngữ (Ollama, OpenRouter) và thực thi các chiến lược hội thoại:
- **`_should_use_legacy(...)`**: Tự động phân tích các biến môi trường để quyết định xem hệ thống có cần chạy chế độ tương thích ngược hay không.
- **`execute(...)`**: Điểm vào duy nhất cho các yêu cầu đồng bộ. Thực hiện tuần tự các bước kiểm tra cấu hình, ưu tiên chạy LangGraph nếu được import thành công, tiếp theo là ReAct Agent và cuối cùng là bộ điều phối Legacy.
- **`execute_stream(...)`**: Điểm vào cho luồng dữ liệu stream. Chỉ hỗ trợ ReAct Agent, tự động chặn các chế độ không tương thích và trả về dòng chảy sự kiện NDJSON trực tiếp cho API.

### B. Dịch vụ Truy xuất Tri thức Y sinh (`RetrievalService`)
Đảm bảo việc tìm kiếm dữ liệu chuẩn hóa từ Graph Database và liên kết với thư viện tri thức Microsoft GraphRAG:
- **`query_langchain_graph_with_sources(...)`**: Thực thi các truy vấn đồ thị chuỗi liên kết phức tạp, bóc tách chính xác các văn bản nguồn và câu trả lời để đóng gói trả về cho lớp API.

---

## 3. Bản đồ các phương thức nghiệp vụ chi tiết

### Lớp dịch vụ `AgentService` (`services/agent_service.py`)
- `__init__(settings, llm_backend)`: Inject cấu hình hệ thống và trình quản lý backend LLM, hỗ trợ chế độ tự động dò quét và kết nối.
- `_run_react(...)`: Thiết lập tham số và vận hành mạch lập luận ReAct kèm bộ đếm giới hạn vòng lặp.
- `_run_legacy(...)`: Vận hành luồng xử lý tuần tự cũ của hệ thống y tế CDSS.
- `is_available()`: Kiểm tra nhanh tình trạng hoạt động và kết nối thông suốt của backend LLM.

### Lớp dịch vụ `RetrievalService` (`services/retrieval_service.py`)
- `query(question, k)`: Thực thi tìm kiếm thông tin lâm sàng thông qua các câu lệnh Cypher tối ưu hóa.

---

## 4. Hướng phát triển nâng cấp (Roadmap)
1. **Circuit Breaker Policy (Cơ chế ngắt mạch)**: Tích hợp chính sách dự phòng tự động (fallback) chuyển đổi từ mô hình ngôn ngữ local (Ollama) sang Cloud API (OpenRouter) khi phát hiện quá tải hoặc mất kết nối.
2. **Comprehensive Telemetry (Đo lường chi tiết)**: Theo dõi thời gian thực thi của từng phân đoạn dịch vụ, thống kê lượng token tiêu thụ và độ trễ để ghi nhận vào hệ thống Log tập trung.
3. **Mock Interfaces**: Chuyển các dịch vụ sang kiến trúc kế thừa Interface giúp dễ dàng mock dữ liệu khi chạy các bài kiểm thử tự động toàn diện.

---
*Xem thêm tài liệu tổng thể tại [README tổng](../README.md).*
