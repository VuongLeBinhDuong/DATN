# Đánh giá Custom KG (Graph-First Retrieval)

Thư mục này đánh giá **Custom KG** (123k+ entities, 987k+ relations) với graph-first retrieval:

- **Entity Coverage**: Có tìm được entities liên quan không?
- **Chunk Recall**: Các chunk retrieved có chứa thông tin cần thiết không?
- **Retrieval Quality**: Precision@K, Recall@K, F1, MRR, NDCG

## Custom KG Schema

```
(:Entity {entity_id, canonical_name, type, aliases})
(:Chunk {chunk_id, doc_id, text, title})
(:Entity)-[:MENTIONS]->(:Chunk)
(:Entity)-[:CO_OCCURS_WITH|REL]->(:Entity)
```

## File chính

| File | Mô tả |
|------|-------|
| `eval_custom_kg.py` | Script đánh giá retrieval trên Custom KG |
| `retrieval_metrics.py` | Metrics: Precision@K, Recall@K, F1, MRR, NDCG |
| `test_queries.jsonl` | Tập câu hỏi test với expected entities |
| `README.md` | Tài liệu này |

## Chạy đánh giá

### 1. Đánh giá đơn giản (quick check)

```powershell
python eval/eval_custom_kg.py --limit 10
```

### 2. Đánh giá đầy đủ với dataset

```powershell
# Cần có file eval/test_queries.jsonl
python eval/eval_custom_kg.py --dataset eval/test_queries.jsonl --out eval/report.md
```

### 3. Với custom K values

```powershell
python eval/eval_custom_kg.py --k 5 10 20 --out eval/report.md
```

## Cấu trúc dataset (test_queries.jsonl)

```json
{
  "id": "q_001",
  "question": "tiểu đường tuýp 2",
  "expected_entities": ["tiểu đường", "đái tháo đường"],
  "expected_types": ["Disease"],
  "expected_chunk_count": 5
}
```

## Metrics giải thích

| Metric | Ý nghĩa |
|--------|---------|
| **Precision@K** | % entities retrieved là relevant |
| **Recall@K** | % relevant entities được retrieved |
| **F1@K** | Cân bằng Precision và Recall |
| **MRR** | Mean Reciprocal Rank (vị trí đầu tiên relevant) |
| **NDCG@K** | Normalized Discounted Cumulative Gain |

## Lưu ý quan trọng

1. **Entity matching**: Dùng `canonical_name` và `aliases` cho synonym matching
   - "tiểu đường" = "đái tháo đường" = "diabetes"

2. **Type filtering**: Có thể filter theo entity type (Disease, Drug, Symptom...)

3. **Chunk vs Entity**: Custom KG retrieval trả về chunks thông qua entity mentions

## Ví dụ kết quả

```
=== Custom KG Retrieval Evaluation ===
Queries: 10
K=5:  Precision=0.82  Recall=0.65  F1=0.72  MRR=0.88  NDCG=0.79
K=10: Precision=0.75  Recall=0.78  F1=0.76  MRR=0.88  NDCG=0.82
```

## Tích hợp với hệ thống

Custom KG là **priority 1** trong routing:

```python
# llm_pipeline/graphrag_query.py
if _custom_kg_available():
    ctx, hits = _run_custom_kg_query(question)
    # hits chứa chunks từ custom KG
```

Endpoint web: `/api/langchain-graph-query/direct`

## So sánh với Microsoft GraphRAG

| | Custom KG | Microsoft GraphRAG |
|--|-----------|-------------------|
| Entities | 123,641 (regex + LLM) | ~10k (LLM only) |
| Relations | 987,292 (CO_OCCURS_WITH + REL) | ~50k (RELATED) |
| Schema | Clean (Entity/Chunk/REL) | Complex (Community/Section) |
| Speed | ⚡ Fast (regex-based) | 🐢 Slow (LLM-based) |
| Explainability | ✅ High | ⚠️ Medium |
| Maintenance | ✅ Easy | ⚠️ Complex |
