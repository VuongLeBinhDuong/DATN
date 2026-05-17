# LangChain GraphRAG for Medical QA

Giải pháp GraphRAG thay thế Microsoft GraphRAG - nhanh hơn, đơn giản hơn.

## Cấu trúc

```
langchain_graphrag/
├── medical_qa_graph.ipynb    # Notebook chính (giống repo mẫu)
├── requirements.txt           # Dependencies
└── README.md                  # Hướng dẫn này
```

## Tích hợp runtime (code Python)

Logic truy vấn Neo4j + synthesis nằm trong repo chính tại [`llm_pipeline/langchain_graphrag.py`](../llm_pipeline/langchain_graphrag.py) (được API [`POST /api/langchain-graph-query`](../api/README.md) và `services/retrieval_service.py` gọi). Notebook trong thư mục này dùng để **build** graph; app chỉ **đọc** graph đã có.

## Quick Start

### 1. Cài dependencies

```bash
cd langchain_graphrag
pip install -r requirements.txt
```

### 2. Chuẩn bị data

Data đã có sẵn từ bước 1 (clean):
- `../graphrag/input/medical_reference_vi_qa.json`

### 3. Chạy notebook

```bash
jupyter notebook medical_qa_graph.ipynb
```

Hoặc chạy từng cell trong VS Code.

## So sánh

| | Microsoft GraphRAG | LangChain (này) |
|---|---|---|
| **Thời gian index** | 30-60 phút | **10-15 phút** |
| **Community reports** | Có | Không |
| **Global search** | Có | Không |
| **Cypher query** | Tự động | **Tự viết** |
| **Debug** | Khó | **Dễ** |

## Lưu ý

- **Thời gian chậm nhất:** Extract entities (~10 phút cho 3000 records)
- **Phụ thuộc:** `qwen2.5:7b` cho entity extraction
- **Vector DB:** Neo4j (dùng chung với Microsoft GraphRAG)

## Tùy chọn nhanh hơn

Chỉ dùng **Vector Search** (bỏ Graph):

```python
# Skip graph extraction, chỉ tạo vector index
vector_index = Neo4jVector.from_documents(
    documents,
    embeddings,
    url=NEO4J_URL,
    username=NEO4J_USER,
    password=NEO4J_PASSWORD,
)
```

→ Thời gian: **2-3 phút**
→ Chất lượng: Vẫn tốt cho RAG thuần

## Sơ đồ luồng notebook LangChain GraphRAG

```text
graphrag/input/medical_reference_vi_qa.json
                    |
                    v
           medical_qa_graph.ipynb
             |               |
             v               v
   extract entities      vector index
             \             /
              \           /
                  Neo4j graph
                      ^
                      |
/api/langchain-graph-query -> llm_pipeline/langchain_graphrag.py -> Answer + sources
```
