# Module Medical Records

## Mục đích

`medical_records/` xử lý hồ sơ y tế tải lên (PDF/Excel), trích xuất chỉ số xét nghiệm, so sánh tham chiếu và tạo tư vấn bổ sung.

## Endpoint liên quan

- Prefix mount tại API: `/api/medical-record`
- Endpoint chính: `POST /api/medical-record/analyze`

## Thành phần chính

| File | Vai trò |
|---|---|
| `api_router.py` | API upload, validate file, parse options |
| `analyze.py` | Pipeline tổng hợp phân tích hồ sơ |
| `pdf_extract.py` | Trích xuất nội dung từ PDF |
| `xlsx_extract.py` | Trích xuất nội dung từ Excel |
| `lab_parse.py` | Parse các dòng chỉ số xét nghiệm |
| `lab_compare_on_form.py` | So sánh giá trị với reference in-form |
| `reference_ranges.py` | Load/cấu hình ngưỡng tham chiếu nội bộ |
| `report_compare_llm.py` | So sánh báo cáo bằng LLM |
| `rag_advice_llm.py` | Tư vấn thêm dựa trên RAG context |
| `pill_image_store.py` | Tra ảnh thuốc từ dataset cục bộ |
| `storage_paths.py` | Xác định đường dẫn lưu upload/extract |

## Chi tiết theo file (hàm / endpoint chính)

| File | Hàm / symbol | Mô tả ngắn |
|---|---|---|
| `api_router.py` | `pill_images_search`, `lab_reference_info`, `analyze_medical_record` | Router FastAPI: tra ảnh thuốc, meta reference, pipeline phân tích upload async. |
| `analyze.py` | `analyze_medical_file`, `compare_to_reference`, `build_llm_summary` | Ghép PDF/XLSX → lab parse → so reference → tuỳ chọn LLM summary / RAG. |
| `record_extract.py` | `extract_text_from_record` | Chọn extractor theo đuôi file. |
| `pdf_extract.py` | `extract_text_from_pdf`, `parse_page_spec` | PyMuPDF, chọn trang. |
| `xlsx_extract.py` | `extract_raw_text_from_xlsx`, `extract_text_from_xlsx`, `extract_structured_rows_from_xlsx` | Đọc sheet, nhận diện bảng xét nghiệm. |
| `lab_parse.py` | `parse_labeled_values`, `to_canonical_value` | Parse cặp nhãn–giá trị từ text. |
| `lab_compare_on_form.py` | `compare_extracted_report_on_form`, `classify_value_against_reference`, `format_on_form_lab_for_llm` | So trên biểu mẫu in-form vs khoảng tham chiếu theo giới. |
| `reference_ranges.py` | `load_reference_config`, `pick_hemoglobin_entry`, `canonical_match` | JSON ngưỡng nội bộ + match nhãn. |
| `report_compare_llm.py` | `llm_compare_result_to_reference_on_report`, `call_report_compare` | So sánh báo cáo bằng LLM. |
| `rag_advice_llm.py` | `build_graphrag_query_from_extract`, `fetch_graphrag_context`, `llm_extract_reasoning_plus_graphrag_advice` | RAG GraphRAG + lời khuyên LLM sau extract. |
| `pill_image_store.py` | `resolve_pill_lookup_query`, `lookup_pill_images`, `format_pill_image_observation`, `enrich_suggested_medications_with_pill_images` | Dataset crawl + cache; dùng bởi `agent/tools`. |
| `storage_paths.py` | `medical_record_upload_dir`, `medical_record_extract_dir`, `cleanup_roots_on_exit`, `pill_image_dataset_dir`, `session_dir_for_cleanup` | Đường dẫn upload/extract và cleanup lifecycle API. |
| `suggest_meds_extract.py` | `extract_suggested_drugs_from_narrative` | Regex/gợi ý thuốc từ văn bản. |

## Luồng xử lý tiêu biểu

1. Nhận file upload và validate định dạng/kích thước.
2. Trích xuất text/table từ PDF hoặc Excel.
3. Parse lab values.
4. So sánh reference (in-form hoặc internal reference config).
5. Bổ sung tư vấn bằng retrieval + LLM (nếu bật).
6. Trả JSON kết quả + metadata file lưu.

## Cấu hình quan trọng

- `MEDICAL_RECORD_MAX_UPLOAD_MB`
- `PILL_IMAGE_DATA_DIR` (qua `storage_paths.py`)
- Các biến LLM backend (`OLLAMA_*`, `OPENROUTER_*`)

## Sơ đồ luồng phân tích hồ sơ y tế

```text
+------------------------+
| Upload PDF/XLSX/XLSM   |
+------------------------+
           |
           v
api_router.analyze_medical_record
           |
           v
      chọn extractor
       |          |
       v          v
 pdf_extract   xlsx_extract
       \          /
        \        /
         text/rows
            |
            v
        lab_parse
            |
            v
   compare_to_reference
            |
            v
   bật tư vấn RAG/LLM?
      |            |
      v            v
rag_advice_llm   trả kết quả luôn
      |
      v
JSON kết quả + metadata
```

## Cần cải thiện

1. Tách xử lý nặng sang async job queue (Celery/RQ + Redis).
2. Chuẩn hóa schema output phân tích để frontend dễ render.
3. Thêm test theo bộ sample hồ sơ y tế thực tế (golden files).

## Liên kết

- README tổng: [`../README.md`](../README.md)
- API module: [`../api/README.md`](../api/README.md)
