# Module Scripts

## Mục đích

`scripts/` chứa các script vận hành dữ liệu, build index, import graph, crawling và đánh giá chất lượng retrieval.

## Danh sách script chính

| Script | Vai trò |
|---|---|
| `build_index.py` | Build index retrieval |
| `graphrag_parquet_to_neo4j.py` | Import output GraphRAG vào Neo4j |
| `eval_graph_rag.py` | Đánh giá graph rag kiểu legacy |
| `eval_retrieval_quality.py` | Đánh giá retrieval quality chuẩn hơn |
| `validate_eval_dataset_neo4j.py` | Validate expected labels với graph thực |
| `analyze_medical_pdf.py` | Phân tích file y tế từ CLI |
| `crawl_reference_pages*.py` | Crawl nguồn tham khảo y khoa |
| `crawl_pill_images_icrawler.py` | Crawl ảnh thuốc |
| `clean_*` | Làm sạch và chuẩn hóa dữ liệu |

## Chi tiết từng script (file → mục đích)

| Script | Chức năng chính |
|---|---|
| `build_index.py` | Build chỉ mục vector / pipeline Milvus tuỳ cấu hình. |
| `graphrag_parquet_to_neo4j.py` | Import parquet GraphRAG sang Neo4j (đồng bộ đồ thị). |
| `eval_graph_rag.py` | Đánh giá Graph RAG theo JSONL (node/edge/groundedness). |
| `eval_retrieval_quality.py` | Đánh giá chất lượng retrieval chi tiết hơn (`--dataset`, `--k`). |
| `validate_eval_dataset_neo4j.py` | Đối chiếu tập eval với thực tế neo4j. |
| `audit_eval_vs_graph_entities.py` | So sánh/thẩm định nhãn eval với entity graph. |
| `analyze_medical_pdf.py` | CLI phân tích PDF y tế (gọi `medical_records`). |
| `crawl_reference_pages.py` | Crawl trang tham khảo (phiên bản gốc). |
| `crawl_reference_pages_vi.py` | Crawl phiên bản tiếng Việt / nguồn VI. |
| `crawl_pill_images_icrawler.py` | Crawl ảnh viên thuốc vào dataset. |
| `clean_reference_data.py`, `clean_vi_qa_data.py`, `clean_vi_medical_data.py` | Chuẩn hóa làm sạch bộ dữ liệu tương ứng. |
| `export_graphrag_graphml.py` | Export đồ thị GraphRAG sang GraphML. |
| `test_langchain_graphrag.py` | Kiểm thử/truy vấn mẫu LangChain graph. |

## Ví dụ lệnh thường dùng

```bash
python scripts/build_index.py
python scripts/graphrag_parquet_to_neo4j.py
python scripts/eval_retrieval_quality.py --dataset eval/graph_eval_set.jsonl --k 5
python scripts/validate_eval_dataset_neo4j.py --dataset eval/graph_eval_set.jsonl
```

## Lưu ý

- Chạy từ root dự án để tránh lỗi import path.
- Một số script cần Neo4j/Ollama đang chạy tùy chức năng.

## Sơ đồ luồng scripts vận hành

```text
data thô + nguồn crawl
        |
        v
    clean_*.py
        |
        v
   build_index.py
        |
        v
  graphrag/output
        |
        v
graphrag_parquet_to_neo4j.py
        |
        v
      Neo4j
        |
        v
eval_graph_rag.py / eval_retrieval_quality.py
        |
        v
    eval/*.md report

analyze_medical_pdf.py -> medical_records/
```

## Cần cải thiện

1. Chuẩn hóa CLI arguments giữa các script (`--config`, `--dry-run`, `--output`).
2. Thêm task runner (Makefile/justfile) để giảm command thủ công.
3. Bổ sung logging/exit-code rõ ràng để tích hợp CI tốt hơn.

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Eval docs: [`../eval/README.md`](../eval/README.md)
