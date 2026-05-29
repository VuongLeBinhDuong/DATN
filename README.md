# Hệ thống Hỗ trợ Quyết định Lâm sàng (CDSS) Y tế thông minh - CDSS GraphRAG
> **Đồ án Tốt nghiệp xuất sắc** tích hợp Đồ thị tri thức liên kết (GraphRAG), Tác tử Nhận thức (Cognitive AI Agents), bộ phân tích bệnh án đa định dạng chuyên sâu và công cụ Trực quan minh chứng Y khoa (Explainable AI - XAI).

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Neo4j Graph Database](https://img.shields.io/badge/Neo4j-008CC1?style=flat&logo=neo4j)](https://neo4j.com/)
[![Ollama Local LLM](https://img.shields.io/badge/Ollama-11434?style=flat)](https://ollama.com/)
[![License: Academic Research Only](https://img.shields.io/badge/License-Academic_Research-blue.svg)](#)

> [!WARNING]
> **Tuyên bố miễn trừ trách nhiệm y khoa**: Hệ thống này được nghiên cứu, thiết kế và phát triển thuần túy cho mục đích nghiên cứu học thuật, tham chiếu kỹ thuật và trình diễn công nghệ y tế. Hệ thống **không thay thế** bất kỳ chẩn đoán, quyết định điều trị lâm sàng, kê đơn hay tư vấn chuyên môn nào của bác sĩ và nhân viên y tế có chứng chỉ hành nghề.

---

## 1. Bản đồ Năng lực Cốt lõi của Hệ thống

Dự án CDSS-GraphRAG phân tách luồng vận hành y khoa thành 4 trụ cột công nghệ chính:

```text
              +-----------------------------------+
              |  [ Yêu cầu lâm sàng từ Người dùng ] |
              +-----------------------------------+
                                |
                                v
                  +---------------------------+
                  |    API ROUTER GATEWAY     |
                  +---------------------------+
                    /                       \
        [Hỏi đáp CDSS Chat]               [Tải Hồ sơ Bệnh án]
                  /                           \
                 v                             v
      +---------------------+       +---------------------+
      |   Tác tử Nhận thức  |       | Bộ phân tích bệnh án|
      |   ReAct Agent Lõi   |       | PDF, Excel (Parser) |
      +---------------------+       +---------------------+
         /               \                     |
        v                 v                    v
  +-----------+     +-----------+       +---------------------+
  | Cơ sở dữ  |     | Microsoft |       | So khớp dải chỉ số  |
  | liệu Neo4j|     | GraphRAG  |       | sinh học chuẩn 0ms  |
  +-----------+     +-----------+       +---------------------+
        \                 |                    /
         \                v                   /
          +-------> [ EXPLAINABLE AI ] <-----+
                    | Trực quan hóa đồ thị   |
                    | động y khoa (XAI)      |
                    +------------------------+
                                |
                                v
                  +---------------------------+
                  |  - Giao diện Web UI CDSS  |
                  |  - Xuất báo cáo PDF       |
                  +---------------------------+
```

1. **Tác tử Tư vấn Lâm sàng Nhận thức (Agentic Medical Consultation)**: Giao diện hội thoại dạng dòng chảy (streaming tokens) thời gian thực sử dụng **Mô hình lập luận ReAct (Reason + Action)**. Agent tự động lập kế hoạch, chọn công cụ, chạy truy vấn đồ thị và tự động sửa định dạng nếu LLM cục bộ phát sinh lỗi.
2. **Truy xuất Đồ thị Tối ưu (Graph-First Retrieval)**: Vượt qua các giới hạn của Vector RAG thông thường bằng cách khai thác trực tiếp các truy vấn đồ thị Neo4j Cypher và công cụ tóm tắt phân cấp cộng đồng từ Microsoft GraphRAG.
3. **Phân tích So sánh Bệnh án Đa tầng (Medical Record Parsing)**: Tự động trích xuất các chỉ số xét nghiệm lâm sàng từ định dạng `.pdf`, `.xlsx`, `.xlsm` thô, so khớp với dải tham chiếu sinh học tiêu chuẩn và tự động sinh cảnh báo đỏ (Red Flags).
4. **Trực quan minh chứng Y khoa (Explainable AI - XAI)**: Tích hợp bản đồ mạng đồ thị thực thể động tương tác (sử dụng Vis.js standalone) ngay trên giao diện chat của nhân viên y tế, thể hiện rõ chuỗi liên kết suy luận lâm sàng (`Triệu chứng -> Bệnh lý -> Thuốc khuyên dùng`).

---

## 2. Đóng góp và Điểm sáng Công nghệ đã Thực hiện

Hệ thống đã triển khai thành công 3 cải tiến công nghệ tự phát triển vượt trội so với các đồ án RAG cơ bản:

### A. Thuật toán ReAct Loop-Guard (Bộ cứu hộ Tác tử thời gian thực)
* **Vấn đề**: Các dòng mô hình nhỏ chạy local (như Llama-3.1-8B) cực kỳ dễ bị lỗi định dạng Markdown của ReAct hoặc rơi vào vòng lặp vô hạn khi gọi công cụ.
* **Giải pháp**: Thiết kế cơ chế giám sát ba tầng (*Loop-Guard*): theo dõi lịch sử hành động, bắt ngoại lệ phân tích cú pháp và tự động định tuyến phục hồi để bảo đảm thời gian phản hồi luôn dưới 3 giây.

### B. Tối ưu hóa & Thu gọn Đồ thị Tri thức (Graph Pruning)
* **Vấn đề**: GraphRAG thô tạo ra hơn 33.000 thực thể bị dán nhãn "Other" chứa các từ nối vô nghĩa, làm loãng ngữ cảnh và chậm truy vấn Cypher.
* **Giải pháp**: Phát triển tập lệnh Cypher quét và lọc tự động, tối ưu đồ thị y học tiếng Việt xuống còn **25.319 thực thể chuyên sâu** và **193.042 quan hệ lâm sàng** chất lượng cao.

### C. Trực quan minh chứng Đồ thị Tri thức (Vis.js Subgraph Viewer)
* **Vấn đề**: Các kết quả trả về từ RAG thông thường giống như "hộp đen", bác sĩ không biết AI dựa trên tài liệu nào để đưa ra khuyến nghị thuốc.
* **Giải pháp**: Trích xuất phân vùng đồ thị liên kết (`context_graphrag_full`) và vẽ biểu đồ các thực thể động (Dynamic Network Graph) trực tiếp dưới luồng chat. Các thực thể như *Disease (Bệnh lý - Đỏ)*, *Drug (Thuốc - Xanh lá)*, *Symptom (Triệu chứng - Vàng)* được phân loại màu sắc và hỗ trợ click hiển thị định nghĩa chi tiết.

---

## 3. Bản đồ Kiến trúc Hệ thống (Clean Architecture)

Hệ thống áp dụng nghiêm ngặt mô hình kiến trúc sạch giúp dễ dàng bảo trì và viết kiểm thử:

```text
Presentation Layer: api/ + web_ui/
   ├── api/main.py (Điểm bắt đầu ứng dụng FastAPI)
   └── web_ui/ (Trang giao diện thuần HTML/CSS/JS, Vis.js, html2pdf)
       
Business Logic Layer: services/ + agent/ + medical_records/
   ├── agent/react/agent.py (Mạch suy nghĩ ReAct & Bộ phục hồi lỗi cú pháp)
   ├── medical_records/analyzer.py (Bộ trích xuất biểu mẫu xét nghiệm y khoa)
   └── services/agent_service.py (Bộ điều phối lựa chọn chiến lược Agent)
       
Data Access Layer: repositories/ + llm_pipeline/ + retrieval/
   ├── repositories/neo4j_repository.py (Thực thi các câu lệnh Cypher tối ưu)
   └── retrieval/graph_retriever.py (Truy xuất lai kết hợp Reranker)
       
Infrastructure & Configuration: core/ + config/ + docker/
   ├── core/config.py (Quản lý thiết lập toàn cục bằng Pydantic Settings)
   └── config/.env (Tệp tin bảo mật chứa thông tin kết nối dịch vụ)
```

---

## 4. Lộ trình Cải tiến Đột phá (Future Roadmap)

Để nâng tầm đồ án y tế CDSS này lên chuẩn sản xuất thương mại và học thuật cao hơn, lộ trình 9 điểm cải tiến sau đã được hoạch định chi tiết:

1. **Cross-Encoder Reranker (Tái xếp hạng nâng cao)**: Tích hợp mô hình `bge-reranker-large` để đánh giá mức độ tương thích ngữ nghĩa sâu giữa câu hỏi của bác sĩ và tri thức đồ thị trước khi đưa vào LLM.
2. **Asynchronous Task Queue (Xử lý bệnh án bất đồng bộ)**: Sử dụng Celery và Redis để phân tách việc tải lên và phân tích PDF/Excel nặng khỏi luồng xử lý chính của máy chủ API.
3. **Multi-Agent Collaboration (Phối hợp đa chuyên khoa)**: Sử dụng LangGraph để phân rã Agent thành các chuyên gia y tế chuyên biệt (Triage Agent, Graph Specialist, Pharmacist Agent) để ra quyết định đồng thuận.
4. **Bộ kiểm duyệt Hướng dẫn lâm sàng (Medical Guardrails)**: Tích hợp Guardrails AI để kiểm soát cứng đầu ra của Agent, đảm bảo mọi lời khuyên sử dụng thuốc phải nằm trong giới hạn cho phép của Bộ Y tế Việt Nam.
5. **OCR đa phương thức (EasyOCR / LMMs)**: Tích hợp Qwen2-VL hoặc EasyOCR để hỗ trợ tải ảnh chụp đơn thuốc, phiếu xét nghiệm thô thay vì chỉ đọc file PDF/Excel định dạng sạch.
6. **Ẩn danh hóa dữ liệu bệnh nhân (HIPAA Compliance)**: Tích hợp Microsoft Presidio để quét và tự động ẩn (masking) thông tin cá nhân PII (Tên, tuổi, SĐT, địa chỉ) trước khi dữ liệu được gửi tới LLM.
7. **Tối ưu hóa mô hình ngôn ngữ nhỏ (Local SLM Fine-tuning)**: Tinh chỉnh (fine-tune) các dòng mô hình cục bộ như Qwen-2.5-7B-Instruct trên bộ dataset y tế chuyên biệt tiếng Việt để cải thiện độ chuẩn xác và tốc độ suy luận.
8. **Kiểm thử y khoa tự động (MMLU-Medical Benchmarking)**: Xây dựng tập kiểm thử tự động đo lường độ chính xác lâm sàng dựa trên bộ câu hỏi trắc nghiệm y khoa chuẩn hóa.
9. **Hệ thống giám sát vận hành LLM (LLMOps & Tracing)**: Kết nối với Langfuse hoặc Arize Phoenix để theo dõi chi phí token, thời gian chạy công cụ và giải trình "luồng tư duy" của tác tử.

---

## 5. Hướng dẫn Khởi chạy và Vận hành

### Yêu cầu hệ thống tối thiểu:
- Docker & Docker Compose
- Python 3.10+
- Hệ thống local có RAM trống từ 16GB (để chạy mượt mà Llama-3.1-8B qua Ollama)

### Khởi động nhanh bằng Docker (Khuyên dùng)
```bash
cd docker
docker compose up --build -d
```
* **Web UI**: [http://localhost:8000/ui/agent.html](http://localhost:8000/ui/agent.html)
* **Neo4j Browser**: [http://localhost:7474](http://localhost:7474) (Tài khoản: `neo4j` / `changeme`)
* **FastAPI Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Thiết lập thủ công cho Nhà phát triển
```bash
# 1. Kích hoạt môi trường ảo
python -m venv .venv
.\.venv\Scripts\activate  # Windows
source .venv/bin/activate  # Linux/macOS

# 2. Cài đặt dependencies
pip install -r requirements.txt

# 3. Kéo mô hình local y tế
ollama pull llama3.1:8b

# 4. Làm sạch dữ liệu và nạp cơ sở dữ liệu đồ thị Neo4j
python scripts/clean_vi_medical_data.py
python scripts/kg_apply_schema.py
python scripts/kg_import_artifacts.py

# 5. Khởi chạy API Server
python -m uvicorn api.main:app --reload
```

---

## 6. Danh mục các câu lệnh Quản trị & Đánh giá cốt lõi

* **Vận hành thử nghiệm ReAct CLI**:
  ```bash
  python -m agent --question "Triệu chứng và chế độ ăn cho bệnh đái tháo đường tuýp 2" --json
  ```
* **Chạy toàn bộ 109 ca kiểm thử tự động**:
  ```bash
  python run_tests.py
  ```
* **Đánh giá chất lượng trích xuất Đồ thị**:
  ```bash
  python eval/eval_custom_kg.py --dataset eval/test_queries.jsonl --out eval/report.md
  ```
* **Đánh giá hiệu năng truy xuất RAG đa tầng**:
  ```bash
  python scripts/eval_retrieval_quality.py --dataset eval/graph_eval_set.jsonl --k 5
  ```

---
*Chúc bạn có một buổi bảo vệ đồ án tốt nghiệp thành công rực rỡ! Đội ngũ phát triển CDSS-GraphRAG.*
