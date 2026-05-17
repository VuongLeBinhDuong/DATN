# Module Repositories

## Mục đích

`repositories/` cung cấp tầng truy cập tri thức theo Repository Pattern, giúp tách logic nghiệp vụ khỏi backend cụ thể.

## Thành phần

| File | Vai trò |
|---|---|
| `base.py` | Định nghĩa `KnowledgeRepository` và model kết quả query |
| `factory.py` | Chọn backend `auto`, `neo4j`, `cli` |
| `neo4j_repo.py` | Query graph trực tiếp bằng Neo4j/Cypher |
| `graphrag_cli_repo.py` | Fallback qua CLI khi Neo4j không dùng được |

## Cách chọn backend

```python
from repositories import get_knowledge_repository

repo = get_knowledge_repository("auto")  # ưu tiên neo4j, fallback cli
result = repo.query("Triệu chứng thiếu máu")
```

## Lưu ý

- Chất lượng Agent phụ thuộc mạnh vào kết quả từ repository.
- `neo4j_repo` thường cho nguồn trích dẫn rõ hơn và latency ổn định hơn khi index tốt.

## Chi tiết theo file

### `base.py`

| Thành phần | Mô tả |
|---|---|
| `QueryResult` | Dataclass/container kết quả: văn bản trả về + danh sách `sources` (dict). |
| `KnowledgeRepository` (ABC) | Interface: phương thức `query` đồng bộ (và tuỳ backend, tham số bổ sung). |

### `factory.py`

| Hàm | Mô tả |
|---|---|
| `get_knowledge_repository(kind)` | `neo4j` \| `cli` \| `auto` — auto: ưu tiên Neo4j nếu config bật và kết nối được, ngược lại CLI GraphRAG. |
| `get_default_repository()` | Wrapper gọi `get_knowledge_repository("auto")` (dùng trong API `Depends`). |

### `neo4j_repo.py`

| Thành phần | Mô tả |
|---|---|
| `_normalize_bolt_uri`, `_fulltext_safe_query`, `_query_to_string` | Tiện ích chuẩn hoá URI / query fulltext / stringify kết quả Cypher. |
| `Neo4jRepository` | Cài đặt `KnowledgeRepository`: truy vấn fulltext + láng giềng, trả text + sources có score. |

### `graphrag_cli_repo.py`

| Thành phần | Mô tả |
|---|---|
| `_resolve_graphrag_data_dir` | Tìm thư mục dữ liệu artifact GraphRAG. |
| `GraphRAGCLIRepository` | Gọi pipeline GraphRAG qua subprocess/CLI khi không dùng Neo4j driver. |

## Cần cải thiện

1. Thêm backend hybrid retrieval (graph + lexical + vector) dưới cùng interface.
2. Bổ sung cache theo query normalized.
3. Chuẩn hóa confidence score giữa các backend.

## Sơ đồ chọn backend retrieval

```text
+--------------------------+
| Query từ service / agent |
+--------------------------+
             |
             v
 +------------------------------+
 | get_knowledge_repository()   |
 +------------------------------+
      |        |         |
      v        v         v
    neo4j     cli       auto
      |        |         |
      |        |    kiểm tra Neo4j
      |        |      |      |
      |        |      v      v
      |        |   dùng neo4j / dùng cli
      v        v
 Neo4jRepo   GraphRAGCLIRepo
      \        /
       \      /
        +------------------------------+
        | QueryResult: text + sources  |
        +------------------------------+
```

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Service layer: [`../services/README.md`](../services/README.md)
