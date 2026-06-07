# Phân hệ Dịch vụ Nghiệp vụ Trung gian (Business Services Layer)
> **Bộ não điều hành nghiệp vụ** nằm ở tầng trung gian của hệ thống CDSS, chịu trách nhiệm nhận yêu cầu xử lý từ API, phân loại ý định qua Intent Router, chọn mô hình lập luận tối ưu (ReAct Agent) và điều phối các cấu phần lâm sàng chuyên biệt.

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
                                   v
                     +-----------------------------+
                     |    1. DETECT INTENT (0ms)   | <-- core.intent_router
                     +-----------------------------+
                       /                         \
         [Ý định direct_db]                    [Ý định RAG / Chẩn đoán]
                     /                             \
                    v                               v
        +-----------------------+         +-----------------------+
        | Định tuyến nhanh 0ms  |         | Vòng Lặp Lập Luận Lõi |
        | (So khớp chỉ số)      |         | ReAct Agent Core      |
        +-----------------------+         +-----------------------+
                    \                               /
                     \                             v
                      +------> [ TRUY XUẤT ] <----+
                               | RetrievalService |
                               +------------------+
                                        |
                                        v
                               +------------------+
                               | Neo4j & GraphRAG |
                               +------------------+
```

---

## 2. Chi tiết các Dịch vụ Nghiệp vụ cốt lõi

### A. Dịch vụ Điều phối Tác tử chuyên nghiệp (`AgentService`)
Chịu trách nhiệm tiếp nhận yêu cầu chẩn đoán, điều phối các backend mô hình ngôn ngữ (Ollama, OpenRouter) và tích hợp bộ định tuyến nhanh:
- **`execute(...)`**: Điểm vào duy nhất cho các yêu cầu đồng bộ. Thực hiện kiểm tra định tuyến 0ms. Nếu câu hỏi yêu cầu so khớp chỉ số sinh học lâm sàng chuẩn, hệ thống tự động xử lý và trả kết quả trong 0ms. Nếu không, nó sẽ kích hoạt bộ lập luận `ReActAgent.run_sync`.
- **`execute_stream(...)`**: Điểm vào cho luồng dữ liệu stream. Tương tự như `execute`, nhưng trả về dòng chảy sự kiện NDJSON trực tiếp cho API thông qua cấu trúc phát trực tiếp `run_stream` của ReAct Agent.

### B. Dịch vụ Truy xuất Tri thức Y sinh (`RetrievalService`)
Đảm bảo việc tìm kiếm dữ liệu chuẩn hóa từ Graph Database:
- **`query_langchain_graph_with_sources(...)`**: Thực thi các truy vấn đồ thị chuỗi liên kết phức tạp, bóc tách chính xác các văn bản nguồn và câu trả lời để đóng gói trả về cho lớp API.

---

## 3. Bản đồ các phương thức nghiệp vụ chi tiết

### Lớp dịch vụ `AgentService` (`services/agent_service.py`)
- `__init__(settings, llm_backend)`: Inject cấu hình hệ thống và trình quản lý backend LLM, hỗ trợ chế độ tự động kết nối.
- `execute(message, strategy, history)`: Kiểm tra định tuyến nhanh trước khi gọi `_run_react`.
- `_run_react(...)`: Thiết lập tham số và vận hành mạch lập luận ReAct.
- `is_available()`: Kiểm tra nhanh tình trạng hoạt động và kết nối thông suốt của backend LLM.

### Lớp dịch vụ `RetrievalService` (`services/retrieval_service.py`)
- `query(question, k)`: Thực thi tìm kiếm thông tin lâm sàng thông qua các câu lệnh Cypher tối ưu hóa.

---
*Xem thêm tài liệu tổng thể tại [README tổng](../README.md).*
