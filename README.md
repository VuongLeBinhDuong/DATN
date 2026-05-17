# DATN - Hệ thống hỏi đáp và tư vấn y khoa thông minh

Đây là dự án đồ án tốt nghiệp xây dựng hệ thống hỏi đáp y khoa dựa trên Retrieval-Augmented Generation (RAG), kết hợp GraphRAG, Agent AI, xử lý hồ sơ y tế và giao diện web.

Cảnh báo y tế: hệ thống chỉ phục vụ mục đích tham khảo kỹ thuật. Không thay thế chẩn đoán, kê đơn hoặc điều trị chuyên môn của bác sĩ.

---

## 1. Tổng quan hệ thống

Hệ thống có 4 nhóm chức năng chính:

- Chat hỏi đáp y khoa qua Agent (mặc định ReAct).
- Truy vấn tri thức GraphRAG trực tiếp qua API.
- Phân tích hồ sơ y tế tải lên (`pdf`, `xlsx`, `xlsm`) và tạo nhận định.
- Cung cấp web UI dùng trực tiếp, không cần build frontend.

## 2. Công nghệ đang sử dụng

### Backend/API
- Python 3.10+
- FastAPI, Uvicorn
- Pydantic + pydantic-settings

### Agent/LLM
- ReAct Agent
- Legacy Orchestrator + chế độ LangGraph
- Ollama (mặc định)
- OpenRouter (tùy chọn)

### Retrieval và tri thức
- Neo4j graph database
- GraphRAG (workspace + artifacts) 
- Milvus vector store
- Sentence Transformers embeddings

### Xử lý dữ liệu và QA
- PyMuPDF (PDF extraction)
- openpyxl (Excel extraction)
- pytest + pytest-cov + pytest-asyncio

### Triển khai
- Docker + Docker Compose (stack chính)

---

## 3. Kiến trúc tổng quan

```text
Presentation: api/ + web_ui/
    ->
Business: services/ + agent/ + medical_records/
    ->
Data Access: repositories/ + rag_milvus/ + llm_pipeline/
    ->
Infra/Config: core/ + config/ + docker/ + deploy/
```

Mẫu thiết kế chính:

- Repository pattern (`repositories/`)
- Dependency injection (`api/dependencies.py`)
- Strategy selection (`services/agent_service.py`)
- ReAct loop (`agent/react/agent.py`)

## 3.1 Sơ đồ luồng tổng hệ thống

```text
+------------------+         +------------------+
|    Người dùng     | ------> |     web_ui/      |
+------------------+         +------------------+
          |                           |
          |                           v
          +------------------> +------------------+
                               |       api/       |
                               +------------------+
                                  |      |      |
                                  |      |      +----> +----------------------+
                                  |      |             | docker/ + deploy/    |
                                  |      |             +----------------------+
                                  |      |
                                  |      +----> +------------------+
                                  |             |      core/       |
                                  |             +------------------+
                                  |
                                  v
                           +------------------+
                           |    services/     |
                           +------------------+
                              |      |      |
                              |      |      +----> +------------------+
                              |      |             | medical_records/ |
                              |      |             +------------------+
                              |      |                        |
                              |      +------------------------+
                              |               gọi LLM/RAG
                              v
                      +------------------+
                      |      agent/      |
                      +------------------+
                        |       |
                        |       +----> +------------------+
                        |              |  llm_pipeline/   |
                        |              +------------------+
                        |                         |
                        |                         v
                        |               +------------------+
                        |               |    prompts/      |
                        |               +------------------+
                        v
                +------------------+        +------------------+
                | repositories/    | -----> | Neo4j/GraphRAG   |
                +------------------+        +------------------+
                        |
                        +---------> +------------------+
                                   |   rag_milvus/    |
                                   +------------------+

+------------------+      +------------------+      +------------------+
|    scripts/      | ---> |      data/       | ---> | repositories/    |
+------------------+      +------------------+      +------------------+

+------------------+
|     config/      |
+------------------+
      |       |
      v       v
   +-----+  +----------+
   |api/ |  |services/ |
   +-----+  +----------+
```

---

## 4. Mục lục README theo từng thư mục

Các README theo module thường có mục **«Chi tiết theo file»** hoặc tương đương (hàm, route, artifact) để tra cứu nhanh khi đọc code — bắt đầu từ đúng thư mục bạn đang sửa.

### Runtime và Application

- [agent/README.md](agent/README.md)
- [api/README.md](api/README.md)
- [core/README.md](core/README.md)
- [services/README.md](services/README.md)
- [repositories/README.md](repositories/README.md)

### Nghiệp vụ và xử lý

- [medical_records/README.md](medical_records/README.md)
- [llm_pipeline/README.md](llm_pipeline/README.md)
- [rag_milvus/README.md](rag_milvus/README.md)
- [prompts/README.md](prompts/README.md)

### Dữ liệu và tri thức

- [graphrag/README.md](graphrag/README.md)
- [data/README.md](data/README.md)
- [backups/README.md](backups/README.md)
- [langchain_graphrag/README.md](langchain_graphrag/README.md)

### Vận hành, QA và UI

- [scripts/README.md](scripts/README.md)
- [web_ui/README.md](web_ui/README.md)
- [config/README.md](config/README.md)
- [docker/README.md](docker/README.md)
- [deploy/README.md](deploy/README.md)
- [eval/README.md](eval/README.md)
- [tests/README.md](tests/README.md)

---

## 5. API endpoint tổng hợp

### Health

- `GET /`
- `GET /health`
- `GET /health/ready`
- `GET /health/config`
- `GET /health/performance`

### GraphRAG

- `GET /ask?q=...`
- `POST /api/query`

### Agent

- `POST /api/agent-query`
- `POST /api/agent-query/stream`
- `POST /api/langchain-graph-query`
- `POST /api/langchain-graph-query/direct`

### Ollama proxy

- `GET /api/ollama/health`
- `POST /api/ollama/chat`

### Medical records

- `GET /api/medical-record/pill-images`
- `GET /api/medical-record/lab-reference`
- `POST /api/medical-record/analyze`

---

## 6. Hướng dẫn chạy nhanh

### Cách 1: Docker (khuyến nghị)

```bash
cd docker
docker compose up --build -d
```

Sau khi chạy:

- UI: `http://localhost:8000/ui/`
- Swagger: `http://localhost:8000/docs`
- Neo4j Browser: `http://localhost:7474`

### Cách 2: Chạy local để phát triển

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy config\.env.example config\.env
python -m uvicorn api.main:app --reload
```

---

## 7. Lệnh thường dùng

```bash
# Agent CLI (ReAct)
python -m agent --question "Triệu chứng bệnh tiểu đường" --json

# Legacy
python -m agent --legacy --question "Phong benh tim mach"

# Legacy + LangGraph
python -m agent --legacy --langgraph --question "Tương tác thuốc A và B"

# Test
pytest -v

# Eval retrieval
python scripts/eval_retrieval_quality.py --dataset eval/graph_eval_set.jsonl --k 5
```

---

## 8. Bien moi truong quan trong

| Bien | Y nghia |
|---|---|
| `OLLAMA_HOST` | URL Ollama |
| `OLLAMA_MODEL` | Model mac dinh |
| `OLLAMA_TIMEOUT` | Timeout request LLM |
| `NEO4J_ENABLED` | Bat/tat truy van Neo4j |
| `NEO4J_URI` | URI ket noi Neo4j |
| `NEO4J_USER` | User Neo4j |
| `NEO4J_PASSWORD` | Password Neo4j |
| `AGENT_USE_REACT` | Bật ReAct mode |
| `AGENT_USE_LEGACY_PIPELINE` | Bật legacy mode |
| `AGENT_REACT_MAX_ITER` | So vong ReAct |
| `RATE_WINDOW_SEC` | Cua so rate limit |
| `RATE_MAX_PER_WINDOW` | Gioi han request |
| `CORS_ORIGINS` | Danh sach CORS |

---

## 9. Nhung diem can cai thien (P0/P1/P2)

### P0

1. Dong bo docs va implementation endpoint/CLI.
2. Bo sung smoke tests cho CLI va endpoint quan trong.
3. Giam test stale sau refactor, tang do tin cay CI.

### P1

1. Hybrid retrieval (graph + lexical + vector).
2. Re-ranking truoc khi dua context vao LLM.
3. Tach xu ly tai lieu nang sang async queue.

### P2

1. Observability day du (metrics/tracing/error monitoring).
2. Secret management va pre-commit security scan.
3. Standard hoa task runner cho run/test/eval/index.

---

## 10. Lưu ý vận hành

- Khong commit secret trong `config/.env`.
- Du lieu trong `docker/ollama/models/` la runtime artifact.
- Nên version hóa dataset/index/backup khi reindex để dễ truy vết.

---

## 11. Tai lieu tham khao

- [FastAPI](https://fastapi.tiangolo.com/)
- [Neo4j Python Driver](https://neo4j.com/docs/python-manual/)
- [Microsoft GraphRAG](https://microsoft.github.io/graphrag/)
- [LangGraph](https://langchain-ai.github.io/langgraph/)
- [Ollama API](https://github.com/ollama/ollama/blob/main/docs/api.md)
- [Milvus](https://milvus.io/docs/)

