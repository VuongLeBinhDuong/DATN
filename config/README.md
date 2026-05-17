# Module Config

## Mục đích

`config/` chứa cấu hình tĩnh và mẫu biến môi trường cho các thành phần chính.

## Thành phần

| File | Vai trò |
|---|---|
| `.env.example` | Mẫu env để khởi tạo cấu hình local |
| `.env` | Env local thực tế (không nên commit secret) |
| `neo4j.json` | Cấu hình kết nối Neo4j |
| `store.json` | Cấu hình vector store |
| `lab_reference_ranges.json` | Ngưỡng tham chiếu xét nghiệm nội bộ |

## Nội dung file JSON (tóm tắt vai trò)

| File | Nội dung tiêu biểu |
|---|---|
| `neo4j.json` | URI Bolt, user, password, optional database — dong bo voi `NEO4J_*` env khi nhap khau. |
| `store.json` | Milvus/vector collection, dim embedding, URI — dong bo `STORE_*`. |
| `lab_reference_ranges.json` | Nguyen toan/canonical label + khoang tham chieu nam/nu — dung boi `medical_records.reference_ranges`. |

## Quy tắc sử dụng

1. Sao chép `config/.env.example` sang `config/.env`.
2. Không đưa API key/password thật lên git.
3. Ưu tiên cập nhật qua env thay vì hardcode trong code.

## Sơ đồ luồng nạp cấu hình

```text
config/.env + .env.example ----+
neo4j.json --------------------+--> core/settings.py --> api/
store.json --------------------+                     --> services/
                                                     --> agent/

lab_reference_ranges.json ---> medical_records/reference_ranges.py
```

## Cần cải thiện

1. Hợp nhất schema config để giảm trùng lặp env + json.
2. Thêm script kiểm tra tính hợp lệ config trước khi chạy.
3. Bổ sung tài liệu mapping biến cấu hình theo từng môi trường.

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Core settings: [`../core/README.md`](../core/README.md)
