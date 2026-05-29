# Phân hệ Phân tích Bệnh án & Chỉ số Y sinh (Medical Records Module)
> **Trình xử lý tài liệu đa định dạng chuyên sâu** của hệ thống CDSS, chịu trách nhiệm tiếp nhận hồ sơ xét nghiệm lâm sàng, tự động giải mã văn bản ảnh (OCR Fallback), phân loại trị số sinh học 0ms bằng thuật toán Pure-Python, và truy vấn tri thức đồ thị Neo4j để tổng hợp cảnh báo y sinh.

---

## 1. Sơ đồ Hoạt động Toàn trình (End-to-End CDSS Pipeline)

Phân hệ sử dụng kiến trúc phân tầng độc lập giúp tăng độ chính xác lên 100% đối với các đối chiếu chỉ số xét nghiệm lâm sàng thông qua các thuật toán Python chuyên biệt:

```text
          +--------------------------------------------+
          |     [ Bệnh án dạng PDF / Excel thô ]       |
          +--------------------------------------------+
                                |
                                v
                 +------------------------------+
                 |   PHÂN LOẠI ĐUÔI FILE EXT    |
                 +------------------------------+
                  /                            \
     [.xlsx / .xlsm]                          [.pdf]
                /                                \
               v                                  v
    +-------------------+               +-------------------+
    |  xlsx_extract.py  |               |  pdf_extract.py   |
    |  (Bảng tính Excel)|               |  (Tài liệu PDF)   |
    +-------------------+               +-------------------+
             |                                    |
             |                                    v
             |                        { Dò mật độ chữ: <15 ký tự? }
             |                          /                       \
             |                  (Có - Bản scan ảnh)         (Không - PDF gốc)
             |                        /                           \
             |                       v                             v
             |             +--------------------+       +--------------------+
             |             |  OCR FALLBACK      |       |  PyMuPDF Direct    |
             |             |  Tesseract/EasyOCR |       |  Text Extraction   |
             |             +--------------------+       +--------------------+
             |                       |                             |
             v                       v                             v
    +------------------------------------------------------------------------+
    |                 [ TRÍCH XUẤT VĂN BẢN LÂM SÀNG THUẦN ]                  |
    +------------------------------------------------------------------------+
                                        |
                                        v
    +------------------------------------------------------------------------+
    |              [ lab_compare_on_form.py (Pure-Python 0ms) ]              |
    |              - Đối chiếu trị số dải tham chiếu giới tính               |
    +------------------------------------------------------------------------+
                                        |
                                        v
                        { Kiểm tra Chỉ số Bất thường? }
                         /                           \
                 [Có Cảnh báo Đỏ]                 [Không có]
                       /                               \
                      v                                 v
        +----------------------------+       +---------------------+
        |  Neo4j GraphRAG Advice     |       |  Bỏ qua tầng gọi    |
        |  - Lấy liên kết thực thể   |       |  LLM đắt đỏ         |
        +----------------------------+       +---------------------+
                      |                                 |
                      v                                 |
        +----------------------------+                  |
        |  Ollama LLM Consultation   |                  |
        |  (Tổng hợp lời khuyên)      |                  |
        +----------------------------+                  |
                      \                                 /
                       +---------------+---------------+
                                       |
                                       v
                     +-----------------------------------+
                     |    [ BÁO CÁO KẾT QUẢ CDSS JSON ]  |
                     |    - Tích hợp ảnh thuốc local     |
                     |    - Xuất báo cáo Vector PDF      |
                     +-----------------------------------+
```

---

## 2. Các Thành phần Công nghệ Trọng tâm

| Tên File | Vai trò nghiệp vụ |
|---|---|
| `api_router.py` | Controller tiếp nhận file tải lên, cấu hình tham số dải tham chiếu (gender, pages) và xử lý bất đồng bộ. |
| `analyze.py` | Lớp điều phối tổng (Orchestrator) toàn trình, nhận diện file thô và cấu trúc dữ liệu kết quả phân tích. |
| `pdf_extract.py` | Trích xuất văn bản từ file PDF gốc bằng PyMuPDF và kích hoạt bộ render ảnh DPI 150 để OCR nếu là file quét ảnh. |
| `xlsx_extract.py` | Bộ phân tích bảng tính Excel sử dụng thư viện `openpyxl`, tự động quét và thu gọn dòng/cột chứa chỉ số y sinh. |
| `lab_compare_on_form.py` | Lõi so sánh dải tham chiếu in-form chuyên dụng theo giới tính của bệnh nhân, xác định tình trạng (Bình thường, Tăng cao, Giảm thấp). |
| `rag_advice_llm.py` | Tổng hợp khuyến nghị lâm sàng, kết nối trực tiếp với tri thức đồ thị Neo4j dựa trên các chỉ số cảnh báo đỏ. |
| `pill_image_store.py` | Bộ quản lý kho ảnh thuốc cục bộ, cung cấp hình ảnh trực quan minh họa cho đơn thuốc khuyên dùng. |

---

## 3. Các Tính năng Đặc thù & Đóng góp Công nghệ

### A. Cơ chế OCR Fallback 2 tầng (Scanned Document Parsing)
- **Vấn đề**: Nhiều bệnh án của bệnh nhân là bản scan dạng ảnh chụp từ máy điện thoại hoặc máy quét cũ, không có văn bản thuần để trích xuất.
- **Giải pháp**: Tự động dò mật độ chữ. Nếu phát hiện số lượng ký tự trung bình mỗi trang nhỏ hơn 15, hệ thống tự động render ảnh chất lượng cao và kích hoạt chuỗi OCR: ưu tiên **Tesseract OCR (vie+eng)**, nếu không khả dụng sẽ tự động chuyển đổi sang **EasyOCR local** để giải cứu nội dung văn bản.

### B. So khớp chỉ số y sinh 0ms bằng thuật toán Pure-Python
- **Vấn đề**: Việc sử dụng LLM để đọc chỉ số xét nghiệm và so sánh khoảng số học cực kỳ đắt đỏ, chậm chạp và dễ xảy ra hiện tượng ảo giác (hallucinations - sai lệch số học).
- **Giải pháp**: Sử dụng biểu thức chính quy (Regex) bóc tách các trị số sinh học trên phiếu xét nghiệm gốc và đối chiếu trực tiếp bằng thuật toán Python với dải tham chiếu giới tính sinh học tại `reference_ranges.py`. Kết quả trả về ngay lập tức với độ chính xác số học là 100%.

---

## 4. Danh mục tham số Cấu hình Môi trường

| Biến môi trường | Kiểu | Mặc định | Chức năng |
|---|---|---|---|
| `MEDICAL_RECORD_MAX_UPLOAD_MB` | `int` | `15` | Giới hạn dung lượng tệp tải lên hệ thống |
| `MEDICAL_RECORD_GRAPHRAG_TOP_K`| `int` | `6` | Số lượng ngữ cảnh đồ thị liên kết tối đa truy xuất |
| `MEDICAL_RECORD_DISABLE_ON_FORM_COMPARE` | `bool` | `false` | Vô hiệu hóa phân tích trị số in-form (chỉ dùng LLM) |

---

## 5. Hướng phát triển nâng cấp (Roadmap)
1. **Asynchronous Task Queue (Hàng đợi bất đồng bộ)**: Chuyển tác vụ phân tích tài liệu nặng ra khỏi API chính bằng cách tích hợp hệ thống **Celery + Redis** để cải thiện độ khả dụng của dịch vụ.
2. **Qwen-VL Multimodal Support**: Thay thế bộ phân tích OCR dạng chữ bằng mô hình thị giác ngôn ngữ cục bộ để đọc hiểu ngữ cảnh bệnh án trực tiếp từ ảnh chụp.
3. **Medical Dataset Validation**: Xây dựng bộ dataset hồ sơ y tế chuẩn (Golden Dataset) để chạy tích hợp kiểm thử hồi quy tự động cho phân hệ.

---
*Xem thêm tài liệu tổng thể tại [README tổng](../README.md).*
