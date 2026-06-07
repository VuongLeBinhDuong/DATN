# Phân hệ Truy xuất Lai ghép tối ưu (Retrieval Module)

> **Lõi truy xuất lai ghép tối ưu (Custom Graph-First Retrieval)** kết hợp topological đồ thị Neo4j, so trùng từ khóa (Lexical search) và bộ tái xếp hạng nơ-ron cục bộ (Neural Cross-Encoder Reranker) cho tiếng Việt.

---

## 1. Thành phần

Thư mục `retrieval/` chứa logic xử lý tìm kiếm và xếp hạng tài liệu trước khi đưa vào LLM:

*   **`graph_first.py`**: Lõi của luồng `Graph-First Retrieve` bao gồm:
    *   **Clinical NER Extraction**: Sử dụng SLM cục bộ để nhận diện nhanh các loại thực thể lâm sàng (`DRUG`, `DISEASE`, `SYMPTOM`, `TEST`).
    *   **Neo4j Path Queries**: Chạy Cypher truy vấn đường đi (1-2 bước) để tìm liên kết trực tiếp giữa các thực thể vừa trích xuất.
    *   **Dual-Channel candidates**: Truy xuất ứng viên từ cả kênh tần suất từ khóa (Lexical) lẫn độ tin cậy đồ thị Neo4j.
    *   **Reciprocal Rank Fusion (RRF)**: Hợp nhất kết quả từ cả hai kênh bằng xếp hạng nghịch đảo RRF.
    *   **Neural Rerank (PhoRanker)**: Tái xếp hạng bằng mô hình Cross-Encoder tiếng Việt cục bộ (`itdainb/PhoRanker`).
    *   **Graph Soft Pruning**: Middleware làm sạch và cắt tỉa nút cô lập (`prune_subgraph`) trước khi trả về sơ đồ mạng lưới.

---

## 2. Cách hoạt động của Custom Graph-First Retrieval

```text
               [ Câu hỏi từ Người dùng ]
                           |
                           v
        +--------------------------------------+
        | 1. Trích xuất thực thể y tế (NER)     |
        +--------------------------------------+
                           |
                           v
        +--------------------------------------+
        | 2. Tìm đường đi liên kết trên Neo4j   |
        +--------------------------------------+
              /                          \
       (Có đường đi)                (Không tìm thấy)
            /                              \
           v                                v
  +------------------+             +-------------------+
  | Expansion Subgraph|             | Dual-Channel RRF  |
  | (Lấy chunks quan |             | (Lexical + Graph  |
  | hệ trực tiếp)    |             |  mentions)        |
  +------------------+             +-------------------+
           \                                /
            v                              v
        +--------------------------------------+
        | 3. Hợp nhất danh sách ứng viên (RRF) |
        +--------------------------------------+
                           |
                           v
        +--------------------------------------+
        | 4. Tái xếp hạng Cross-Encoder        |  <-- itdainb/PhoRanker
        +--------------------------------------+
                           |
                           v
        +--------------------------------------+
        | 5. Cắt tỉa đồ thị (Pruning)          |  <-- prune_subgraph
        +--------------------------------------+
                           |
                           v
             [ Trả về Context & Đồ thị ]
```

---

## 3. Các tham số cấu hình trong `.env`

Bộ truy xuất có thể tinh chỉnh các tham số sau trong tệp cấu hình:

| Biến môi trường | Kiểu dữ liệu | Mặc định | Vai trò |
|---|---|---|---|
| `KG_USE_RERANKER` | `bool` | `true` | Bật/tắt tầng tái xếp hạng nơ-ron Cross-Encoder |
| `KG_USE_LLM_RERANK` | `bool` | `false` | Bật/tắt tái xếp hạng nhẹ bằng LLM chát |
| `KG_RERANKER_MODEL` | `str` | `itdainb/PhoRanker` | Model Cross-Encoder tiếng Việt chạy cục bộ |

---
*Xem thêm tài liệu tổng thể tại [README tổng](../README.md).*
