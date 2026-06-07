# Hệ thống Hỗ trợ Quyết định Lâm sàng (CDSS) Y tế Thông minh sử dụng GraphRAG

> **Đồ án Tốt nghiệp cử nhân Công nghệ thông tin** tích hợp Đồ thị tri thức y khoa (Custom Clinical Knowledge Graph), Truy xuất lai đa tầng kết hợp Tái xếp hạng nơ-ron (Triangulated Hybrid Retrieval & Neural Reranking), Tác tử Nhận thức ReAct (Cognitive AI Agents) và Trực quan hóa minh chứng y học (Explainable AI - XAI).

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Neo4j Graph Database](https://img.shields.io/badge/Neo4j-008CC1?style=flat&logo=neo4j)](https://neo4j.com/)
[![Ollama Local LLM](https://img.shields.io/badge/Ollama-11434?style=flat)](https://ollama.com/)
[![License: Academic Research](https://img.shields.io/badge/License-Academic_Research-blue.svg)](#)

> [!WARNING]
> **Tuyên bố miễn trừ trách nhiệm y khoa**: Hệ thống này được nghiên cứu, thiết kế và phát triển thuần túy cho mục đích nghiên cứu học thuật, tham chiếu kỹ thuật và trình diễn công nghệ y tế hỗ trợ quyết định (CDSS). Hệ thống **không thay thế** bất kỳ chẩn đoán, quyết định điều trị lâm sàng, kê đơn hay tư vấn chuyên môn nào của bác sĩ và nhân viên y tế có chứng chỉ hành nghề.

---

## 1. Bản đồ Kiến trúc Vận hành Hệ thống

Dự án CDSS-GraphRAG phân tách luồng vận hành y khoa thành 4 trụ cột công nghệ chính:

```text
              +-----------------------------------+
              |  [ Yêu cầu lâm sàng từ Người dùng ] |
              +-----------------------------------+
                                |
                                v
                  +---------------------------+
                  |  HYBRID INTENT ROUTER     |  <-- Zero-LLM Fast Path (Regex) &
                  +---------------------------+      Lightweight SLM (Qwen2.5-1.5B)
                    /                       \
        [Hỏi đáp CDSS Chat]               [Tải Hồ sơ Bệnh án]
                  /                           \
                 v                             v
      +---------------------+       +---------------------+
      |   Tác tử Nhận thức  |       | Bộ phân tích bệnh án|
      |   ReAct Agent Lõi   |       | PDF, Excel (Parser) |
      +---------------------+       +---------------------+
                 |                             |
                 v                             v
      +---------------------------------------------------+
      |         CUSTOM GRAPH-FIRST RETRIEVAL PIPELINE     |
      | 1. Clinical NER -> Neo4j Cypher Path (1-2 Hops)   |
      | 2. Dual-Channel (Lexical Overlap + Graph Mentions)|
      | 3. Reciprocal Rank Fusion (RRF) -> Candidate Top20|
      | 4. Neural Cross-Encoder Rerank (itdainb/PhoRanker)|
      +---------------------------------------------------+
                                |
                                v
                  +---------------------------+
                  |    EXPLAINABLE AI (XAI)   |
                  |  - Trực quan hóa Vis.js   |  <-- Sơ đồ triệu chứng - bệnh - thuốc
                  |  - Xuất báo cáo y tế PDF   |  <-- Tự động tính toán cảnh báo đỏ
                  +---------------------------+
```

1. **Bộ điều phối Intent Router Lai**: Tối ưu chi phí và độ trễ bằng cách lọc nhanh các câu hỏi tra cứu chỉ số cơ bản qua biểu thức chính quy (0ms), hoặc sử dụng mô hình ngôn ngữ siêu nhỏ (SLM - Qwen2.5-1.5B) chạy song song để phân loại mục đích sử dụng trước khi gọi tác tử ReAct.
2. **Tác tử Nhận thức ReAct (ReAct Agent Core)**: Thực thi luồng chẩn đoán suy luận qua cấu trúc lập luận lặp (`Action` -> `Action Input` -> `Observation` -> `Thought`). Được trang bị bộ tự động sửa lỗi cú pháp định dạng (Parse-Retry) và bộ giám sát vòng lặp vô hạn (Loop-Guard) giúp hệ thống luôn hoạt động ổn định trên các mô hình 8B chạy cục bộ.
3. **Đường ống Truy xuất Lai Đồ thị (Custom Graph-First Retrieval)**: Vượt trội hơn các mô hình Vector RAG thông thường bằng cách tích hợp cả liên kết topo đồ thị và độ tương quan ngữ nghĩa qua 4 bước xử lý khép kín (NER path query, Dual-Channel candidates, RRF fusion, và PhoRanker Cross-Encoder).
4. **Bộ phân tích Bệnh án & Chỉ số Xét nghiệm**: Tự động bóc tách chỉ số sinh học từ file PDF/Excel thô, so sánh trực tiếp với dải tham chiếu chuẩn để hiển thị cảnh báo lâm sàng và xuất báo cáo y khoa dạng PDF chính thức chỉ với một click.

---

## 2. Chi tiết Cấu trúc Thư mục Nguồn (Project Structure)

```text
DATN/
├── agent/                      # Lõi điều phối AI Agent
│   └── react/                  # Luồng suy luận ReAct & Loop-Guard, Parse-Retry
├── api/                        # Presentation Layer - fastapi endpoints
│   ├── routes/                 # Routers (auth, agent, graphrag, health, ollama)
│   └── main.py                 # Điểm khởi chạy ứng dụng FastAPI
├── config/                     # Cấu hình môi trường và dịch vụ
│   ├── .env                    # Tham số môi trường (API keys, models, rate limits)
│   ├── neo4j.json              # Thiết lập kết nối cơ sở dữ liệu Neo4j
│   └── store.json              # Thiết lập cơ sở dữ liệu Vector (Milvus)
├── core/                       # Thành phần lõi hạ tầng hệ thống
│   ├── settings.py             # Quản lý cấu hình tập trung sử dụng Pydantic Settings
│   ├── connection_pool.py      # Quản lý kết nối driver Neo4j tối ưu
│   └── intent_router.py        # Định tuyến nhanh ý định chẩn đoán (Fast-Path/SLM)
├── eval/                       # Bộ công cụ đánh giá khoa học
│   ├── test_queries.jsonl      # Bộ câu hỏi thử nghiệm lâm sàng
│   └── eval_custom_kg.py       # Đánh giá Precision@K, Recall@K, F1-Score, MRR
├── kg/                         # Xây dựng & Quản lý Đồ thị Tri thức (Knowledge Graph)
│   ├── extract/                # Tập lệnh trích xuất thực thể (Regex + LLM Relation)
│   ├── models.py               # Định nghĩa các bản ghi (Document, Chunk, Entity, Relation)
│   └── neo4j_client.py         # Client tương tác Cypher với Neo4j
├── medical_records/            # Bộ phân tích dữ liệu bệnh án lâm sàng
│   ├── lab_compare_on_form.py  # So khớp dải chỉ số sinh học chuẩn trích xuất từ form
│   └── rag_advice_llm.py       # Kết hợp phân tích xét nghiệm và khuyến nghị từ Graph
├── retrieval/                  # Bộ xử lý truy xuất dữ liệu nâng cao
│   └── graph_first.py          # Lõi lai ghép đồ thị (RRF) & Tái xếp hạng PhoRanker
├── report/                     # Báo cáo Luận văn Tốt nghiệp bằng LaTeX
├── scripts/                    # Scripts bổ trợ nạp dữ liệu và kiểm thử
├── tests/                      # Bộ test tự động (110 ca kiểm thử API & Logic)
└── web_ui/                     # Giao diện người dùng Web CDSS (HTML/CSS/JS, Vis.js)
```

---

## 3. Các Đột phá Công nghệ đã Hiện thực hóa

### A. Tái xếp hạng nơ-ron Cross-Encoder Tiếng Việt (`itdainb/PhoRanker`)
* **Vấn đề**: Các đoạn văn bản truy xuất từ đồ thị thường bị loãng thông tin do chứa từ khóa trùng khớp nhưng ngữ nghĩa thực tế lệch với triệu chứng bệnh nhân.
* **Giải pháp**: Tích hợp mô hình Cross-Encoder chuyên sâu cho tiếng Việt `itdainb/PhoRanker` ở tầng cuối cùng. Mô hình sẽ đánh giá tương quan trực diện giữa câu hỏi lâm sàng và 20 đoạn văn bản ứng viên tốt nhất từ RRF, chỉ chọn ra top-5 có điểm số cao nhất.
* **Kết quả**: Tối ưu hóa kích thước ngữ cảnh nạp vào LLM, giúp cải thiện **Precision@5 từ 0.160 lên 0.245** và triệt tiêu 60% nhiễu ngữ cảnh.

### B. Thuật toán Làm sạch & Pruning Đồ thị Tri thức Lâm sàng
* **Vấn đề**: Đồ thị tri thức sinh ra từ các bộ trích xuất thô thường chứa hàng ngàn nút rác (dạng hội thoại thông thường như "cảm ơn", "vinmec") và nhiều node bị cô lập (degree = 0) làm loãng sơ đồ và giảm tốc độ truy vấn Cypher.
* **Giải pháp**: Xây dựng thuật toán lọc nhiễu tự động `prune_subgraph(subgraph, seed_ids)` thực hiện lọc bỏ thực thể vô nghĩa bằng regex, hủy các liên kết không đạt ngưỡng tin cậy, và lược bỏ các nút cô lập nhưng giữ lại thực thể gốc (seeds) để bảo toàn khả năng truy xuất.
* **Kết quả**: Làm gọn đồ thị y học xuống còn **25.319 thực thể** và **193.042 quan hệ chất lượng**, tăng tốc độ phản hồi truy xuất Cypher xuống **dưới 80ms**.

### C. Trực quan hóa Minh chứng Y khoa Động (Interactive XAI)
* **Vấn đề**: Các hệ thống RAG thông thường hoạt động như một "hộp đen", không đưa ra được bằng chứng cấu trúc liên kết để bác sĩ kiểm chứng.
* **Giải pháp**: Tích hợp thư viện đồ thị Vis.js động trên Web UI. Tự động chuyển đổi ngữ cảnh chẩn đoán y tế thành sơ đồ mạng lưới thực thể. 
* **Điểm nhấn**: 
  - Tự động phân loại màu sắc các nhóm đối tượng: *Disease (Bệnh lý - Đỏ)*, *Drug (Thuốc - Xanh lá)*, *Symptom (Triệu chứng - Vàng)*.
  - Phân tách kích thước thực thể dựa trên độ ưu tiên: Các thực thể gốc (seeds) được gán điểm ưu tiên (`score = 2.0`) sẽ hiển thị to hơn, viền đậm hơn giúp bác sĩ nhận biết ngay trọng tâm phân tích.

---

## 4. Hướng dẫn Cài đặt và Khởi chạy

### Yêu cầu hệ thống tối thiểu
* Windows 10/11 hoặc Ubuntu 20.04+
* Python 3.10+
* RAM tối thiểu 16GB (Khuyên dùng GPU NVIDIA CUDA nếu muốn tăng tốc chạy PhoRanker và Ollama)
* Docker & Docker Compose (nếu chạy qua Docker)

### Các bước cài đặt thủ công

1. **Khởi tạo môi trường ảo & Cài đặt thư viện**:
   ```bash
   python -m venv .venv
   # Windows:
   .\.venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

2. **Cấu hình môi trường**:
   * Sao chép file cấu hình mẫu: `cp config/.env.example config/.env`
   * Mở file `config/.env` và cập nhật các cấu hình kết nối Neo4j, mô hình Ollama, hoặc API key nếu cần.

3. **Cài đặt & Kéo mô hình local**:
   * Khởi động Ollama local và tải các mô hình cần thiết:
     ```bash
     ollama pull llama3.1:8b
     ollama pull qwen2.5:1.5b-instruct
     ```

4. **Nạp cơ sở dữ liệu đồ thị Neo4j**:
   * Đảm bảo Neo4j đang chạy (mặc định tại `bolt://127.0.0.1:7687` với tài khoản `neo4j` / `changeme`).
   * Chạy các tập lệnh nạp dữ liệu y khoa:
     ```bash
     python scripts/clean_vi_medical_data.py
     python scripts/kg_apply_schema.py
     python scripts/kg_import_artifacts.py
     ```

5. **Khởi chạy API Server**:
   ```bash
   python -m uvicorn api.main:app --reload
   ```
   * Truy cập giao diện Web UI CDSS tại: [http://localhost:8000/ui/agent.html](http://localhost:8000/ui/agent.html)

---

## 5. Hướng dẫn Chạy Kiểm thử & Đánh giá hệ thống

* **Chạy bộ test tự động kiểm tra tính đúng đắn của 110 ca kiểm thử**:
  ```bash
  python run_tests.py
  ```
* **Đánh giá hiệu năng trích xuất đồ thị tri thức Custom KG**:
  ```bash
  python eval/eval_custom_kg.py --dataset eval/test_queries.jsonl --out eval/report.md
  ```

---
*Chúc bạn có một buổi bảo vệ đồ án tốt nghiệp xuất sắc và thành công rực rỡ!*
