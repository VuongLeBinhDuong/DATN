# 🏥 Hệ thống Hỗ trợ Quyết định Lâm sàng (CDSS) Y tế Thông minh sử dụng GraphRAG

> **Đồ án Tốt nghiệp Cử nhân Công nghệ Thông tin** tích hợp Đồ thị Tri thức Y khoa (Custom Clinical Knowledge Graph), Truy xuất lai đa tầng kết hợp Tái xếp hạng nơ-ron (Triangulated Hybrid Retrieval & Neural Reranking), Tác tử Nhận thức ReAct (Cognitive AI Agents) và Trực quan hóa minh chứng y học (Explainable AI - XAI).

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Neo4j Graph Database](https://img.shields.io/badge/Neo4j-008CC1?style=flat&logo=neo4j)](https://neo4j.com/)
[![Ollama Local LLM](https://img.shields.io/badge/Ollama-11434?style=flat)](https://ollama.com/)
[![License: Academic Research](https://img.shields.io/badge/License-Academic_Research-blue.svg)](#)

> [!WARNING]
> **Tuyên bố miễn trừ trách nhiệm y khoa**: Hệ thống này được nghiên cứu, thiết kế và phát triển thuần túy cho mục đích nghiên cứu học thuật, tham chiếu kỹ thuật và trình diễn công nghệ y tế hỗ trợ quyết định (CDSS). Hệ thống **không thay thế** bất kỳ chẩn đoán, quyết định điều trị lâm sàng, kê đơn hay tư vấn chuyên môn nào của bác sĩ và nhân viên y tế có chứng chỉ hành nghề.

---

## 1. Bản đồ Kiến trúc Vận hành Thực tế của Hệ thống

Để tối ưu hóa hiệu năng, giảm độ trễ (từ ~15 giây xuống dưới 1.5 giây) và đảm bảo tính chính xác tuyệt đối, hệ thống đã được tái cấu trúc loại bỏ các luồng LangGraph cồng kềnh. Luồng vận hành thực tế của hệ thống hiện nay được chia thành hai luồng xử lý độc lập:

### 1.1 Luồng Tác tử Hội thoại CDSS (Chat Agent Flow)

```text
[ Yêu cầu lâm sàng từ Người dùng ]
                 |
                 v
   [ BỘ ĐIỀU PHỐI TINH GỌN (AgentService) ]
                 |
        { Kiểm tra Xã giao / Mở đầu (Heuristic Regex - 0ms) }
         /                                           \
    (Khớp - Social)                           (Không khớp - Chẩn đoán)
       /                                               \
      v                                                 v
[ Phản hồi trực tiếp ]                         [ TÁC TỬ NHẬN THỨC REACT CORE ]
(Direct LLM - 0ms RAG)                         (Llama 3.2:3b reasoning loop)
                                                        |
                                            { Lập luận qua các Công cụ }
                                             - graphrag_query (Neo4j / CLI)
                                             - pill_image_lookup
                                             - medical_calculator
                                             - drug_interaction_checker
                                                        |
                                                        v
                                             [ Câu trả lời CDSS cuối cùng ]
                                             - Minh chứng đồ thị Vis.js
                                             - Ảnh thuốc minh họa
```

* **Bộ chặn Xã giao Heuristic (0ms)**: Sử dụng các biểu thức chính quy (Regex) tối ưu hóa trong [agent/router.py](file:///d:/DATN/agent/router.py) để nhận diện nhanh các câu chào hỏi, cảm ơn hoặc xin phép hỏi. Các yêu cầu này được chuyển hướng trực tiếp tới LLM để phản hồi ngay lập tức, tiết kiệm 100% tài nguyên và thời gian gọi Agent.
* **Tác tử Nhận thức ReAct Core**: Đối với các câu hỏi bệnh lý hoặc yêu cầu chẩn đoán, [AgentService](file:///d:/DATN/services/agent_service.py) sẽ kích hoạt [ReActAgent](file:///d:/DATN/agent/react/agent.py) chạy trên mô hình chính (mặc định Llama 3.2:3b). Tác tử thực hiện chuỗi tư duy `Thought` -> gọi công cụ chuyên biệt để sinh `Observation` -> lặp lại tối đa 5 lần trước khi đưa ra khuyến nghị cuối cùng (`Final Answer`).

---

### 1.2 Luồng Phân tích Hồ sơ & Bệnh án (Document Analyzer Flow)

```text
[ Bệnh án dạng PDF / Excel thô ]
                 |
                 v
   [ BỘ PHÂN TÍCH BỆNH ÁN (analyze.py) ]
                 |
      { Trích xuất văn bản (PyMuPDF / openpyxl) }
                 |
      { Tự động kích hoạt OCR Fallback nếu là bản scan }
                 |
                 v
   [ SO KHỚP CHỈ SỐ Y SINH (lab_compare_on_form - 0ms) ]
   (Pure-Python - Đối chiếu dải tham chiếu giới tính sinh học)
                 |
      { Có chỉ số bất thường? }
       /                    \
   (Có)                    (Không)
     /                        \
    v                          v
[ GraphRAG Retrieval ]    [ Bỏ qua LLM đắt đỏ ]
(Neo4j context)                |
    |                          |
    v                          |
[ LLM Synthesis Advice ]       |
(Ollama / OpenRouter)          |
    \                          /
     v                        v
[ Báo cáo kết quả CDSS cuối cùng ]
- Tải ảnh thuốc minh họa
- Xuất báo cáo PDF Vector
```

* **Bộ trích xuất đa định dạng & OCR Fallback**: Đọc dữ liệu từ PDF hoặc Excel. Nếu mật độ ký tự trong PDF quá thấp (<15 ký tự/trang), hệ thống tự động render ảnh DPI 150 và kích hoạt Tesseract OCR / EasyOCR để khôi phục văn bản.
* **So khớp chỉ số 0ms bằng Pure-Python**: Trích xuất các chỉ số xét nghiệm lâm sàng và đối chiếu trực tiếp với dải tham chiếu giới tính tại [reference_ranges.py](file:///d:/DATN/medical_records/reference_ranges.py). Bộ so khớp số học này chạy bằng code Python thuần (0ms), loại bỏ hoàn toàn hiện tượng ảo giác số học của LLM.
* **Tư vấn tích hợp GraphRAG**: Nếu phát hiện chỉ số bất thường (cảnh báo đỏ), hệ thống sẽ tự động dùng tên chỉ số đó làm query để truy xuất ngữ cảnh y khoa tương ứng từ Neo4j Graph Database rồi gửi sang LLM để tổng hợp báo cáo tư vấn.

---

## 2. Chi tiết Cấu trúc Thư mục Nguồn (Project Structure)

```text
DATN/
├── agent/                      # Lõi điều phối AI Agent
│   ├── react/                  # Luồng suy luận ReAct, Loop-Guard, Regex-Healer, Prompts
│   ├── langgraph_app.py        # Luồng Legacy dùng LangGraph (Legacy)
│   ├── orchestrator.py         # Luồng điều phối tuần tự truyền thống (Legacy)
│   ├── router.py               # Chứa bộ lọc xã giao Heuristic và LLM-based Router (Legacy)
│   ├── tools.py                # Lớp trung gian thực thi công cụ đặc hiệu của ReAct
│   ├── medication_tools.py     # Công cụ trích xuất thực thể dược học lâm sàng
│   └── retrieval_confidence.py # Thuật toán đánh giá độ tin cậy của ngữ cảnh RAG
├── api/                        # Presentation Layer - fastapi endpoints
│   ├── routes/                 # Routers (auth, agent, graphrag, health, ollama)
│   ├── dependencies.py         # Dependencies cho rate limit, IP client
│   └── main.py                 # Điểm khởi chạy ứng dụng FastAPI
├── config/                     # Cấu hình môi trường và dịch vụ
│   ├── .env                    # Tham số cấu hình (API keys, models, rate limits)
│   ├── neo4j.json              # Thiết lập kết nối cơ sở dữ liệu Neo4j
│   └── store.json              # Thiết lập cơ sở dữ liệu Vector (Milvus)
├── core/                       # Thành phần lõi hạ tầng hệ thống
│   ├── settings.py             # Quản lý cấu hình tập trung sử dụng Pydantic Settings
│   ├── connection_pool.py      # Quản lý kết nối driver Neo4j tối ưu
│   ├── intent_router.py        # Định tuyến ý định chẩn đoán (Fast-Path/SLM) (Thử nghiệm)
│   ├── llm_backends.py         # Quản lý LLM Backends (Ollama local, OpenRouter)
│   └── cache.py                # Cơ chế cache cho truy vấn LLM
├── eval/                       # Bộ công cụ đánh giá khoa học
│   ├── test_queries.jsonl      # Bộ câu hỏi thử nghiệm lâm sàng
│   └── eval_custom_kg.py       # Đánh giá Precision@K, Recall@K, F1-Score, MRR
├── kg/                         # Xây dựng & Quản lý Đồ thị Tri thức (Knowledge Graph)
│   ├── extract/                # Tập lệnh trích xuất thực thể (Regex + LLM Relation)
│   ├── models.py               # Định nghĩa các bản ghi (Document, Chunk, Entity, Relation)
│   └── neo4j_client.py         # Client tương tác Cypher với Neo4j
├── medical_records/            # Bộ phân tích dữ liệu bệnh án lâm sàng
│   ├── lab_compare_on_form.py  # So khớp dải chỉ số sinh học chuẩn trích xuất từ form
│   ├── pdf_extract.py          # Trích xuất văn bản từ tài liệu PDF (Direct & Scanned OCR)
│   ├── xlsx_extract.py         # Trích xuất dữ liệu từ bảng tính Excel
│   ├── analyze.py              # Lớp điều phối tổng (Orchestrator) phân tích hồ sơ
│   ├── pill_image_store.py     # Quản lý kho ảnh thuốc cục bộ
│   └── rag_advice_llm.py       # Kết hợp phân tích xét nghiệm và khuyến nghị từ Graph
├── retrieval/                  # Bộ xử lý truy xuất dữ liệu nâng cao
│   └── graph_first.py          # Lõi lai ghép đồ thị (RRF) & Tái xếp hạng PhoRanker
├── report/                     # Báo cáo Luận văn Tốt nghiệp bằng LaTeX
├── scripts/                    # Scripts bổ trợ nạp dữ liệu, crawling và kiểm thử
├── tests/                      # Bộ test tự động (109 ca kiểm thử API & Logic)
└── web_ui/                     # Giao diện người dùng Web CDSS (HTML/CSS/JS, Vis.js)
```

---

## 3. Các Đột phá Công nghệ đã Hiện thực hóa

### A. Tái xếp hạng nơ-ron Cross-Encoder Tiếng Việt (`itdainb/PhoRanker`)
* **Vấn đề**: Các đoạn văn bản truy xuất từ đồ thị thường bị loãng thông tin do chứa từ khóa trùng khớp nhưng ngữ nghĩa thực tế lệch với triệu chứng bệnh nhân.
* **Giải pháp**: Tích hợp mô hình Cross-Encoder chuyên sâu cho tiếng Việt `itdainb/PhoRanker` ở tầng cuối cùng của đường ống [graph_first.py](file:///d:/DATN/retrieval/graph_first.py). Mô hình sẽ đánh giá tương quan trực diện giữa câu hỏi lâm sàng và 20 đoạn văn bản ứng viên tốt nhất từ RRF, chỉ chọn ra top-5 có điểm số cao nhất.
* **Kết quả**: Tối ưu hóa kích thước ngữ cảnh nạp vào LLM, giúp cải thiện **Precision@5 từ 0.160 lên 0.245** và triệt tiêu 60% nhiễu ngữ cảnh.

### B. Thuật toán Làm sạch & Pruning Đồ thị Tri thức Lâm sàng
* **Vấn đề**: Đồ thị tri thức sinh ra từ các bộ trích xuất thô thường chứa hàng ngàn nút rác (dạng hội thoại thông thường như "cảm ơn", "vinmec") và nhiều node bị cô lập (degree = 0) làm loãng sơ đồ và giảm tốc độ truy vấn Cypher.
* **Giải pháp**: Xây dựng thuật toán lọc nhiễu tự động `prune_subgraph(subgraph, seed_ids)` trong [neo4j_client.py](file:///d:/DATN/kg/neo4j_client.py) thực hiện lọc bỏ thực thể vô nghĩa bằng regex, hủy các liên kết không đạt ngưỡng tin cậy, và lược bỏ các nút cô lập nhưng giữ lại thực thể gốc (seeds) để bảo toàn khả năng truy xuất.
* **Kết quả**: Làm gọn đồ thị y học xuống còn **25.319 thực thể** và **193.042 quan hệ chất lượng**, tăng tốc độ phản hồi truy xuất Cypher xuống **dưới 80ms**.

### C. Cơ chế Dự phòng Đa tầng (Repository Pattern & LLM Fallback)
* **Vấn đề**: Database Neo4j hoặc mô hình Ollama chạy local có thể bị mất kết nối đột ngột trong quá trình vận hành, gây crash hệ thống CDSS.
* **Giải pháp**: 
  - **Data Fallback**: Áp dụng Repository Pattern tại [repositories/factory.py](file:///d:/DATN/repositories/factory.py). Khi gọi truy vấn, hệ thống tự động kiểm tra trạng thái hoạt động của Neo4j. Nếu online, sử dụng `Neo4jRepository`. Nếu offline, tự động chuyển hướng (fallback) sang `GraphRAGCLIRepository` để chạy truy xuất cục bộ bằng Microsoft GraphRAG CLI.
  - **LLM Fallback**: Logic điều phối LLM tại [core/llm_backends.py](file:///d:/DATN/core/llm_backends.py) hỗ trợ cấu hình dự phòng. Nếu Ollama local gặp sự cố hoặc quá tải, hệ thống tự động fallback lên API đám mây (OpenRouter) để duy trì hoạt động thông suốt.

### D. Cơ chế Giải cứu Định dạng & Loop-Guard của ReAct Agent
* **Vấn đề**: Các mô hình ngôn ngữ nhỏ (nhỏ hơn 8B tham số) chạy local rất dễ gặp lỗi định dạng JSON khi gọi Tool, hoặc bị rơi vào vòng lặp logic vô hạn (infinite loop) gây treo hệ thống.
* **Giải pháp**:
  - **Loop-Guard**: Được cài đặt tại [agent/react/agent.py](file:///d:/DATN/agent/react/agent.py). Giới hạn số vòng lặp chẩn đoán tối đa (`AGENT_REACT_MAX_ITER = 5`). Nếu vượt ngưỡng (LLM lặp đi lặp lại cùng một công cụ), hệ thống kích hoạt cơ chế `_forced_finalize_answer`, tự động tóm tắt từ ngữ cảnh đồ thị hiện tại để đưa ra câu trả lời cứu hộ an toàn trong dưới 3 giây.
  - **Regex-Healer (Format Recovery)**: Cài đặt tại [agent/react/parser.py](file:///d:/DATN/agent/react/parser.py). Sử dụng biểu thức chính quy (Regex) để tự động sửa chữa các lỗi cú pháp định dạng sinh ra bởi LLM (như thiếu dấu ngoặc nhọn, viết sai tên tool, dư thừa ký tự) và trích xuất câu trả lời thô trực tiếp từ văn bản bị lỗi.

### E. So khớp Chỉ số Y sinh 0ms bằng thuật toán Pure-Python & OCR Fallback
* **Vấn đề**: Việc sử dụng LLM để đọc chỉ số xét nghiệm và so sánh khoảng số học cực kỳ đắt đỏ, chậm chạp và dễ xảy ra hiện tượng ảo giác (hallucinations - sai lệch số học). Đồng thời, nhiều bệnh án chỉ ở dạng ảnh scan thô không thể trích xuất chữ.
* **Giải pháp**:
  - **Pure-Python Matcher**: Sử dụng biểu thức chính quy bóc tách các trị số sinh học trên phiếu xét nghiệm gốc và đối chiếu trực tiếp bằng thuật toán Python với dải tham chiếu tại [medical_records/reference_ranges.py](file:///d:/DATN/medical_records/reference_ranges.py) theo giới tính sinh học của bệnh nhân. Trả về kết quả ngay lập tức (0ms) với độ chính xác số học là 100%.
  - **OCR Fallback**: Cài đặt tại [medical_records/pdf_extract.py](file:///d:/DATN/medical_records/pdf_extract.py). Hệ thống tự động phát hiện mật độ chữ (<15 ký tự/trang). Nếu là tài liệu scan, hệ thống tự động render ảnh DPI 150 và kích hoạt chuỗi OCR: ưu tiên **Tesseract OCR**, nếu không khả dụng sẽ tự động chuyển đổi sang **EasyOCR local** để giải cứu nội dung văn bản bệnh án.

### F. Trực quan hóa Minh chứng Y khoa Động (Interactive XAI)
* **Vấn đề**: Các hệ thống RAG thông thường hoạt động như một "hộp đen", không đưa ra được bằng chứng cấu trúc liên kết để bác sĩ kiểm chứng.
* **Giải pháp**: Tích hợp thư viện đồ thị Vis.js động trên Web UI ([web_ui/agent.html](file:///d:/DATN/web_ui/agent.html)). Tự động chuyển đổi ngữ cảnh chẩn đoán y tế thành sơ đồ mạng lưới thực thể. 
* **Điểm nhấn**: 
  - Tự động phân loại màu sắc các nhóm đối tượng: *Disease (Bệnh lý - Đỏ)*, *Drug (Thuốc - Xanh lá)*, *Symptom (Triệu chứng - Vàng)*.
  - Phân tách kích thước thực thể dựa trên độ ưu tiên: Các thực thể gốc (seeds) được gán điểm ưu tiên (`score = 2.0`) sẽ hiển thị to hơn, viền đậm hơn giúp bác sĩ nhận biết ngay trọng tâm phân tích.

---

## 4. Hướng dẫn Cài đặt và Khởi chạy

### Yêu cầu hệ thống tối thiểu
* **HĐH**: Windows 10/11 hoặc Ubuntu 20.04+
* **Python**: Phiên bản 3.10+
* **RAM**: Tối thiểu 16GB (Khuyên dùng GPU NVIDIA CUDA nếu muốn tăng tốc chạy PhoRanker và Ollama)
* **Docker & Docker Compose** (để khởi chạy Neo4j Stack)

### Các bước cài đặt thủ công

1. **Khởi tạo môi trường ảo & Cài đặt thư viện**:
   ```bash
   python -m venv .venv
   # Kích hoạt trên Windows (PowerShell):
   .\.venv\Scripts\Activate.ps1
   # Kích hoạt trên Linux/macOS:
   source .venv/bin/activate

   # Nâng cấp pip và cài đặt dependencies
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

2. **Cấu hình tham số môi trường**:
   * Sao chép file cấu hình mẫu: `cp config/.env.example config/.env`
   * Mở file `config/.env` và cập nhật các cấu hình kết nối Neo4j, mô hình Ollama, hoặc API key nếu cần.

3. **Cài đặt & Kéo mô hình local (Ollama)**:
   * Khởi động Ollama local trên máy tính của bạn.
   * Tải các mô hình cần thiết:
     ```bash
     ollama pull llama3.2:3b
     ollama pull qwen2.5:1.5b-instruct
     ```

4. **Khởi chạy Cơ sở dữ liệu đồ thị Neo4j (Docker Compose)**:
   * Đảm bảo Docker Desktop đang hoạt động.
   * Khởi chạy Neo4j container ở chế độ chạy ngầm:
     ```bash
     docker-compose up -d
     ```
   * Truy cập bảng điều khiển Neo4j Browser tại: [http://localhost:7474](http://localhost:7474) (Tài khoản mặc định: `neo4j` / `changeme`).

5. **Nạp dữ liệu đồ thị tri thức (Ingestion)**:
   Bạn có thể chọn một trong hai cách sau để xây dựng dữ liệu đồ thị Neo4j:

   * **Lựa chọn A: Nạp dữ liệu siêu tốc từ Đồ thị đã trích xuất sẵn (Khuyên dùng - Tiết kiệm thời gian)**:
     1. Tải toàn bộ các tệp dữ liệu đã được trích xuất sẵn (`.jsonl`) tại: [Kaggle Dataset](https://www.kaggle.com/datasets/binhduongvuongle/knowledge-graph-data-about-medical-consultant).
     2. Giải nén tất cả các tệp tin này vào thư mục [kg/kg_artifacts/](file:///d:/DATN/kg/kg_artifacts).
     3. Khởi chạy các tập lệnh nạp dữ liệu siêu tốc chỉ mất vài giây đến 1 phút:
        ```bash
        python scripts/kg_apply_schema.py
        python scripts/kg_import_artifacts.py
        ```

   * **Lựa chọn B: Nạp và trích xuất dữ liệu y khoa từ đầu (Từ nguồn dữ liệu thô)**:
     1. Chạy các lệnh tải dữ liệu từ Hugging Face:
        ```bash
        python scripts/download_additional_medical_data.py
        python scripts/download_vietnamese_medical_qa.py
        python scripts/download_hf_dataset.py
        ```
     2. Chạy các tập lệnh làm sạch và tiến hành trích xuất thực thể/quan hệ bằng LLM (Quá trình này tốn nhiều thời gian và chi phí tính toán):
        ```bash
        python scripts/clean_vi_medical_data.py
        python scripts/clean_vi_qa_data.py
        python scripts/kg_apply_schema.py
        python scripts/kg_extract_entities.py --only-missing
        python scripts/kg_extract_relations.py --only-missing
        ```

6. **Khởi chạy FastAPI Backend Server**:
   ```bash
   python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload
   ```

7. **Truy cập Giao diện Người dùng Web UI**:
   * Trang giao diện chat CDSS & Vis-Network: [http://127.0.0.1:8000/ui/agent.html](http://127.0.0.1:8000/ui/agent.html)
   * Trang tải lên & Phân tích bệnh án: [http://127.0.0.1:8000/ui/nhap-tai-lieu.html](http://127.0.0.1:8000/ui/nhap-tai-lieu.html)
   * Trang thiết lập nhắc lịch uống thuốc: [http://127.0.0.1:8000/ui/lich-nhac.html](http://127.0.0.1:8000/ui/lich-nhac.html)
   * Trang công cụ y tế (BMI/eGFR) & Check tương tác thuốc: [http://127.0.0.1:8000/ui/cong-cu.html](http://127.0.0.1:8000/ui/cong-cu.html)

---

## 5. Hướng dẫn Chạy Kiểm thử & Đánh giá hệ thống

* **Chạy bộ test tự động kiểm tra tính đúng đắn của 109 ca kiểm thử**:
  ```bash
  python run_tests.py
  ```
  *(Hoặc chạy trực tiếp qua lệnh pytest)*:
  ```bash
  pytest -v
  ```

* **Đánh giá hiệu năng trích xuất đồ thị tri thức Custom KG**:
  ```bash
  python eval/eval_custom_kg.py --dataset eval/test_queries.jsonl --out eval/report.md
  ```

* **Đánh giá chất lượng retrieval đa chiều (Precision, Recall, MRR, F1)**:
  ```bash
  python scripts/eval_retrieval_quality.py --dataset eval/graph_eval_set.jsonl --k 5
  ```

* **Đối chiếu tập dữ liệu dự kiến của đồ án với dữ liệu Neo4j thực tế**:
  ```bash
  python scripts/validate_eval_dataset_neo4j.py --dataset eval/graph_eval_set.jsonl
  ```

---
*Chúc bạn có một buổi bảo vệ đồ án tốt nghiệp xuất sắc và thành công rực rỡ!*
