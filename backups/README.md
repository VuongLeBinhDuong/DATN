# Module Backups

## Mục đích

`backups/` lưu snapshot dữ liệu quan trọng tại các thời điểm vận hành (ví dụ trước reindex).

## Cấu trúc snapshot gợi ý trong `manifest.json`

Nên có: `timestamp` (ISO), `description` (lý do backup), phiên bản pipeline/Neo4j, checksum tùy chọn các thư mục `data/`, `graphrag_output/`, `neo4j_export/` — chi tiết tùy quy trình nội bộ.

## Nội dung điển hình

Ví dụ thư mục snapshot:

- `pre_reindex_20260408_210120/`
  - `manifest.json`
  - `data/`
  - `graphrag_output/`
  - `neo4j_export/`

## Khuyến nghị sử dụng

1. Tạo snapshot trước các thao tác phá vỡ như reindex hoặc import lớn.
2. Ghi rõ metadata trong `manifest.json` (thời gian, nguồn, người thực hiện).
3. Kiểm tra khả năng restore định kỳ.

## Sơ đồ luồng backup/restore

```text
Hệ thống đang chạy
        |
        v
   Tạo snapshot backup
      |      |       |
      v      v       v
manifest   data/  graphrag_output/ + neo4j_export/
      |
      v
kiểm tra checksum/integrity
      |
      v
khôi phục khi cần
      |
      v
hệ thống sau restore
```

## Cần cải thiện

1. Chuẩn hóa naming backup theo timestamp ISO.
2. Thêm script backup/restore tự động.
3. Lưu checksum để kiểm tra toàn vẹn backup.

## Liên kết

- README tổng: [`../README.md`](../README.md)
- Data docs: [`../data/README.md`](../data/README.md)
