# Phân hệ API Gateway (FastAPI Presentation Layer)
> **Cổng giao tiếp chuẩn RESTful & Event Stream** của hệ thống CDSS, chịu trách nhiệm nhận yêu cầu từ ứng dụng khách, xác thực thực thể dữ liệu đầu vào, kiểm soát tần suất truy cập (rate-limiting) và điều phối dịch vụ lâm sàng.

---

## 1. Sơ đồ Kiến trúc Luồng Request

API Gateway được xây dựng theo mô hình **Presentation Layer** trong triết lý Clean Architecture, đảm bảo hoàn toàn độc lập với các logic nghiệp vụ lõi:

```text
     +-------------------------------------------------+
     |            [ Trình duyệt / UI Client ]          |
     +-------------------------------------------------+
                              |
                              | HTTP POST/GET
                              v
     +-------------------------------------------------+
     |              [ FASTAPI GATEWAY ]                |
     +-------------------------------------------------+
                              |
                              | Dependency Injection
                              v
     +-------------------------------------------------+
     |             [ api/dependencies.py ]             |
     +-------------------------------------------------+
                              |
                              v
                 [ Kiểm tra IP Rate Limiter ]
                 /                         \
       [Vượt quá Tần suất]            [Tần suất Hợp lệ]
               /                             \
              v                               v
    +-------------------+           +-------------------+
    |     HTTP 429      |           | api/routes/*.py   |
    | Too Many Requests |           | (Điều hướng route)|
    +-------------------+           +-------------------+
                                              |
                                              v
                                    +-------------------+
                                    |    services/*     |
                                    | (Lớp nghiệp vụ)   |
                                    +-------------------+
                                              |
                                              v
                                    +-------------------+
                                    | agent / repos     |
                                    | (Truy xuất lõi)   |
                                    +-------------------+
                                              |
                              +---------------+
                              | Trả kết quả ngược luồng
                              v
     +-------------------------------------------------+
     |       [ Kết quả JSON / SSE Stream NDJSON ]       |
     +-------------------------------------------------+
                              |
                              v
     +-------------------------------------------------+
     |           [ Giao diện Client Web UI ]           |
     +-------------------------------------------------+
```

---

## 2. Chi tiết Cấu trúc Phân mục

- **`main.py`**: Khởi tạo ứng dụng FastAPI, cấu hình chính sách CORS, tích hợp Middleware xử lý lỗi toàn cục, định nghĩa các thư mục tài nguyên tĩnh (`/ui/`, `/api/pill-images/static`) và nạp các bộ định tuyến phân hệ.
- **`dependencies.py`**: Trụ cột quản lý vòng đời phụ thuộc (Dependency Injection), kiểm soát tần suất truy cập in-memory rate-limiter, cung cấp các singleton thể hiện cho Settings, LLM Backend và Knowledge Repository.
- **`routes/`**: Thư mục chứa các module điều hướng phân loại theo nhóm chức năng y tế:
  - `routes/health.py`: Endpoint giám sát hiệu năng hệ thống, tài nguyên RAM/CPU, và kiểm tra tính sẵn sàng của Neo4j và Ollama.
  - `routes/graphrag.py`: Endpoint truy vấn đồ thị tri thức trực tiếp.
  - `routes/agent.py`: Trục kết nối tác tử lâm sàng, hỗ trợ Server-Sent Events (SSE) streaming cho hội thoại nhận thức.
  - `routes/ollama.py`: Proxy kết nối và tương tác trực tiếp với mô hình local.
  - `routes/medical_record.py`: Phân tích hồ sơ xét nghiệm đa định dạng và quản lý dải sinh học tham chiếu.

---

## 3. Các API & Endpoint Lâm sàng Quan trọng

### A. Tác tử Hội thoại Y tế (SSE Streaming)
* **Endpoint**: `POST /api/agent-query/stream`
* **Mô tả**: Nhận câu hỏi y tế cùng lịch sử hội thoại dạng JSON, thực hiện dựng dòng sự kiện SSE trả về cho trình duyệt.
* **Payload đầu vào**:
  ```json
  {
    "message": "Phác đồ và khuyến nghị dinh dưỡng cho bệnh nhân tiểu đường tuýp 2",
    "strategy": "auto",
    "use_react": true,
    "backend": "auto",
    "history": []
  }
  ```

### B. Phân tích Bệnh án Đa định dạng (Multi-part Upload)
* **Endpoint**: `POST /api/medical-record/analyze`
* **Mô tả**: Nhận file bệnh án xét nghiệm (`.pdf`, `.xlsx`, `.xlsm`) cùng dải tham chiếu giới tính của bệnh nhân, trả về phân tích chỉ số y sinh và gợi ý thuốc lâm sàng.

---

## 4. Quản lý Bảo mật & Rate Limiting

Hệ thống bảo vệ tài nguyên tính toán local (LLM Inference rất nặng) thông qua cơ chế lọc tần suất tích hợp sẵn tại `dependencies.py`:
- **Thuật toán**: Monotonic timestamp sliding window.
- **Cấu hình**: Tối đa cho phép `RATE_MAX_PER_WINDOW` request trong vòng `RATE_WINDOW_SEC` giây trên mỗi địa chỉ IP. Vượt ngưỡng sẽ tự động phản hồi mã lỗi `HTTP 429 Too Many Requests`.

---

## 5. Lộ trình Cải tiến Cốt lõi (Future Roadmap)
1. **Chuẩn hóa Envelope Response**: Định dạng toàn bộ phản hồi API theo chuẩn duy nhất gồm `{ status: "success/error", data: ..., error: { code: ..., message: ... } }`.
2. **OpenAPI Schema chi tiết**: Bổ sung đầy đủ dữ liệu mẫu (Examples) và ghi chú học thuật cho tất cả các endpoint trong tài liệu Swagger `/docs`.
3. **JWT Authentication Layer**: Tích hợp xác thực phân quyền nhân viên y tế (Bác sĩ, Dược sĩ, Kỹ thuật viên xét nghiệm) sử dụng mã hóa token.

---
*Xem thêm tài liệu tổng thể tại [README tổng](../README.md).*
