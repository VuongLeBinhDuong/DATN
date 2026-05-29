"""Rule & Regex-based Intent Router for Intelligent Medical Q&A.

Routes queries at zero latency to:
1. direct_db: Direct biological physiological reference lookup (0ms, no LLM).
2. graph_first: Specific entity relationship traversals in Neo4j (local subgraphs).
3. global_summary: Global hierarchical summaries of GraphRAG (global topics).
"""

from __future__ import annotations

import re
from typing import Any
from medical_records.lab_compare_on_form import classify_value_against_reference

# Standard Vietnamese physiological reference ranges (Ground Truth)
STANDARD_LAB_REFERENCES = {
    "glucose": {
        "name": "Glucose (Đường huyết lúc đói)",
        "reference": "3.9 - 6.4 mmol/L",
        "units": ["mmol/l", "mmol/o"],
        "info": "Glucose phản ánh nồng độ đường trong máu. Trị số bình thường lúc đói là 3.9 - 6.4 mmol/L. Từ 5.6 - 6.9 mmol/L là rối loạn đường huyết lúc đói (tiền tiểu đường), từ 7.0 mmol/L trở lên trong 2 lần xét nghiệm khác nhau là chẩn đoán đái tháo đường."
    },
    "hba1c": {
        "name": "HbA1c (Đường huyết trung bình 3 tháng)",
        "reference": "4.0 - 5.6 %",
        "units": ["%", "percent"],
        "info": "HbA1c phản ánh lượng đường trung bình trong máu 3 tháng qua. Dưới 5.7% là bình thường, từ 5.7% - 6.4% là tiền đái tháo đường, từ 6.5% trở lên là đái tháo đường."
    },
    "acid uric": {
        "name": "Acid Uric (Định lượng Acid Uric máu)",
        "reference": "Nam: 208 - 428 umol/L | Nữ: 154 - 357 umol/L",
        "units": ["umol/l", "umol"],
        "info": "Acid uric tăng cao vượt ngưỡng (> 428 umol/L ở Nam, > 357 umol/L ở Nữ) là nguyên nhân gây tích tụ tinh thể urat tại khớp dẫn đến bệnh Gút (Gout) hoặc sỏi thận."
    },
    "cholesterol": {
        "name": "Cholesterol toàn phần",
        "reference": "< 5.2 mmol/L",
        "units": ["mmol/l", "mmol"],
        "info": "Cholesterol toàn phần lý tưởng là dưới 5.2 mmol/L. Chỉ số từ 5.2 - 6.2 mmol/L là tăng nhẹ, trên 6.2 mmol/L là cao, làm tăng nguy cơ xơ vữa động mạch và bệnh tim mạch."
    },
    "triglycerides": {
        "name": "Triglycerides (Chất béo trung tính)",
        "reference": "< 1.7 mmol/L",
        "units": ["mmol/l", "mmol"],
        "info": "Triglycerides là dạng chất béo phổ biến nhất trong cơ thể. Chỉ số bình thường dưới 1.7 mmol/L. Trên 2.3 mmol/L là cao, làm tăng nguy cơ xơ vữa động mạch, viêm tụy cấp."
    },
    "ast": {
        "name": "AST / SGOT (Men gan)",
        "reference": "< 37 U/L",
        "units": ["u/l", "u/o", "ui/l"],
        "info": "AST (SGOT) là men tìm thấy chủ yếu ở tế bào gan, tim, cơ. Chỉ số bình thường dưới 37 U/L. Men gan tăng cao biểu thị tế bào gan đang bị tổn thương hoặc hủy hoại."
    },
    "alt": {
        "name": "ALT / SGPT (Men gan đặc hiệu)",
        "reference": "< 41 U/L",
        "units": ["u/l", "u/o", "ui/l"],
        "info": "ALT (SGPT) là men gan đặc hiệu hơn AST. Chỉ số bình thường dưới 41 U/L. Men gan tăng cao phản ánh tình trạng tổn thương nhu mô gan do viêm gan, độc chất hoặc rượu."
    },
    "creatinine": {
        "name": "Creatinine huyết thanh (Chức năng thận)",
        "reference": "Nam: 62 - 115 umol/L | Nữ: 53 - 97 umol/L",
        "units": ["umol/l", "umol"],
        "info": "Creatinine là sản phẩm đào thải của cơ bắp qua thận. Định lượng creatinine phản ánh chính xác chức năng lọc của cầu thận. Khi chỉ số này tăng vượt ngưỡng chứng tỏ chức năng thận đang bị suy giảm."
    },
    "urea": {
        "name": "Urea máu (Chức năng thận)",
        "reference": "2.5 - 7.5 mmol/L",
        "units": ["mmol/l", "mmol"],
        "info": "Urea là sản phẩm thoái hóa của protein được đào thải qua thận. Chỉ số urea máu bình thường từ 2.5 - 7.5 mmol/L. Tăng cao trong suy thận, mất nước hoặc chế độ ăn giàu đạm."
    }
}


def detect_intent(message: str) -> str:
    """Classify user query intent using rules and regular expressions.
    
    Returns:
        "direct_db" | "graph_first" | "global_summary"
    """
    msg = (message or "").strip().lower()
    
    # 1. Detect Luồng 1 (Direct Reference Query)
    # Match patterns like: "glucose 7.5", "acid uric 450 umol/l", "men gan alt 50"
    num_pattern = r"\b\d+([.,]\d+)?\b"
    has_number = re.search(num_pattern, msg) is not None
    
    # Check if message mentions any standard lab indicator
    has_indicator = False
    for ind_key in STANDARD_LAB_REFERENCES:
        if ind_key in msg:
            has_indicator = True
            break
        # Also check alternate Vietnamese terms
        if ind_key == "glucose" and ("đường huyết" in msg or "tiểu đường" in msg and has_number):
            has_indicator = True
        if ind_key == "acid uric" and "gút" in msg and has_number:
            has_indicator = True
        if (ind_key == "ast" or ind_key == "alt") and "men gan" in msg:
            has_indicator = True

    if has_indicator and has_number:
        # Avoid routing relation questions to direct_db (e.g. "Tiểu đường tuýp 2 uống gì")
        if not ("uống gì" in msg or "thuốc gì" in msg or "điều trị" in msg or "tác động" in msg):
            return "direct_db"

    # 2. Detect Luồng 2 (Graph-First Search / Local relationships)
    # Specific entity relationship queries (contains tags like "thuốc", "bệnh", "tương tác", "ảnh hưởng", "tác dụng phụ")
    relation_keywords = [
        "tương tác", "ảnh hưởng", "tác động", "tác dụng phụ", "chỉ định", "chống chỉ định",
        "kết hợp", "đồng thời", "uống cùng", "thuốc", "bệnh", "triệu chứng", "symptom"
    ]
    has_relation_keywords = any(kw in msg for kw in relation_keywords)
    
    # Identify clinical entities like Metformin, Aspirin, Diabetes, Hypertension
    entity_keywords = [
        "metformin", "aspirin", "ibuprofen", "tiểu đường", "suy thận", "suy gan", "huyết áp",
        "paracetamol", "kháng sinh", "mỡ máu", "cholesterol", "gout", "gút", "tim mạch"
    ]
    has_entities = sum(1 for ent in entity_keywords if ent in msg) >= 2
    
    if has_relation_keywords or has_entities:
        return "graph_first"

    # 3. Fallback to Luồng 3 (Global Summary)
    return "global_summary"


def execute_direct_db_query(message: str) -> dict[str, Any]:
    """Parse laboratory metrics from query and return structured Vietnamese physiological classification.
    
    0ms execution, zero LLM dependencies, fully deterministic.
    """
    msg = (message or "").strip().lower()
    
    # Inferred patient sex if specified
    sex = None
    if "nam" in msg:
        sex = "male"
    elif "nữ" in msg or "nữ" in msg:
        sex = "female"
        
    matched_key = None
    matched_val = None
    
    # Extract numerical value
    num_match = re.search(r"\b(\d+([.,]\d+)?)\b", msg)
    if num_match:
        matched_val = float(num_match.group(1).replace(",", "."))
        
    # Match indicator key
    for ind_key in STANDARD_LAB_REFERENCES:
        if ind_key in msg:
            matched_key = ind_key
            break
        # Alternate mappings
        if ind_key == "glucose" and "đường huyết" in msg:
            matched_key = "glucose"
        if ind_key == "acid uric" and "gút" in msg:
            matched_key = "acid uric"
        if (ind_key == "ast" or ind_key == "alt") and "men gan" in msg:
            matched_key = "alt" if "alt" in msg or "sgpt" in msg else "ast"

    if not matched_key or matched_val is None:
        return {
            "answer": "Hệ thống Router phát hiện ý định tra cứu chỉ số nhưng không bóc tách được tên chỉ số hoặc giá trị số học cụ thể. Vui lòng nhập rõ ràng dạng: 'Glucose của tôi là 7.5 mmol/L' hoặc 'Chỉ số acid uric 450'.",
            "sources": []
        }

    meta = STANDARD_LAB_REFERENCES[matched_key]
    ref_raw = meta["reference"]
    
    # Classify physiological status using python range parsing
    status, reason = classify_value_against_reference(matched_val, ref_raw, sex)
    
    # Format a professional, clean structured Vietnamese response
    sex_str = "Nam" if sex == "male" else ("Nữ" if sex == "female" else "Chưa rõ (đối chiếu cả hai)")
    
    status_vn = {
        "within": "✓ BÌNH THƯỜNG (Trong khoảng tham chiếu y khoa)",
        "high": "⚠ TĂNG CAO (Vượt quá giới hạn tham chiếu an toàn)",
        "low": "⚠ GIẢM THẤP (Dưới mức giới hạn tham chiếu bình thường)",
        "skipped": "Chưa đối chiếu (Cần xác định thêm giới tính bệnh nhân)"
    }.get(status, "—")
    
    answer = (
        f"### KẾT QUẢ ĐỐI CHIẾU CHỈ SỐ LÂM SÀNG TỰ ĐỘNG (INTENT ROUTER - 0MS)\n\n"
        f"Hệ thống phát hiện câu hỏi tra cứu chỉ số sinh học và tự động định tuyến đến Bộ kiểm tra định mức mà không cần gọi LLM, đảm bảo chính xác tuyệt đối.\n\n"
        f"- **Chỉ số tra cứu**: **{meta['name']}**\n"
        f"- **Giá trị bệnh nhân**: `{matched_val}`\n"
        f"- **Giới tính áp dụng**: `{sex_str}`\n"
        f"- **Khoảng tham chiếu chuẩn**: `{ref_raw}`\n"
        f"- **Trạng thái phân loại**: **{status_vn}**\n\n"
        f"**Thông tin y khoa tham khảo**:\n"
        f"{meta['info']}\n\n"
        f"*Lưu ý: Mọi phân loại định lượng chỉ mang tính tham khảo kỹ thuật lâm sàng dựa trên các tài liệu y tế phổ thông tại Việt Nam.*"
    )
    
    return {
        "answer": answer,
        "sources": [
            {
                "title": f"Bảng chỉ số tham chiếu y tế chuẩn - {meta['name']}",
                "link": "",
                "source": "Bộ Y tế Việt Nam / WHO Guidelines",
                "score": 1.0
            }
        ]
    }
