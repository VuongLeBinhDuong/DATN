"""Fallback regex-based entity extractor for high recall.

Dùng khi LLM extraction miss entities hoặc làm bước đầu để tăng recall.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from kg.models import EntityRecord, MentionRecord

# Common Vietnamese medical terms (extend as needed)
MEDICAL_PATTERNS = [
    # Diseases - Bệnh
    (r"\b(tiểu đường(?:\s+tu[ýy]p\s*\d+)?|đái tháo đường|tiểu đường thai k[ỳy])\b", "Disease"),
    (r"\b(huyết áp cao|huyết áp thấp|tăng huyết áp|hạ huyết áp)\b", "Disease"),
    (r"\b(tim mạch|bệnh tim|suy tim|nhồi máu cơ tim|loạn nhịp tim|đau tim)\b", "Disease"),
    (r"\b(gan nhiễm mỡ|viêm gan\s*[ABCE]?|xơ gan|suy gan|ung thư gan)\b", "Disease"),
    (r"\b(sỏi thận|suy thận|viêm thận|ung thư thận)\b", "Disease"),
    (r"\b(ung thư\s*(phổi|dạ dày|ruột|vú|tử cung|tiền liệt tuyến|da|gan|thực quản|buồng trứng|cổ tử cung))\b", "Disease"),
    (r"\b(carcinoma|sarcoma|melanoma|lymphoma|leukemia)\b", "Disease"),
    (r"\b(cúm|covid[-\s]?19|coronavirus|sars|mers)\b", "Disease"),
    (r"\b(viêm phổi|hen suyễn|COPD|tắc nghẽn phổi mãn tính|viêm phế quản)\b", "Disease"),
    (r"\b(viêm dạ dày|loét dạ dày|trào ngược dạ dày thực quản)\b", "Disease"),
    (r"\b(viêm ruột|hội chứng ruột kích thích|IBS|viêm đại tràng)\b", "Disease"),
    (r"\b(tiêm chủng|vaccine)\b", "Disease"),
    (r"\b(dị ứng|mề đay|nhọt|chàm|eczema)\b", "Disease"),
    (r"\b(gout|thống phong)\b", "Disease"),
    (r"\b(thiếu máu)\b", "Disease"),
    (r"\b(béo phì|thừa cân)\b", "Disease"),
    (r"\b(trầm cảm|lo âu|rối loạn lo âu|rối loạn hoảng loạn)\b", "Disease"),
    (r"\b(bệnh Alzheimer|Parkinson|xơ vữa động mạch)\b", "Disease"),
    (r"\b(bệnh thận đa nang|bệnh thận mạn)\b", "Disease"),
    (r"\b(bệnh tiểu đường thai kỳ)\b", "Disease"),
    (r"\b(bệnh cường giáp|bệnh suy giáp)\b", "Disease"),
    (r"\b(bệnh lupus|bệnh tự miễn)\b", "Disease"),
    (r"\b(bệnh viêm khớp dạng thấp)\b", "Disease"),
    (r"\b(bệnh đa xơ cứng)\b", "Disease"),
    # Symptoms - Triệu chứng
    (r"\b(đau đầu|chóng mặt|buồn nôn|nôn|tiêu chảy|táo bón)\b", "Symptom"),
    (r"\b(sốt|ho|khó thở|đau ngực|đau bụng)\b", "Symptom"),
    (r"\b(mệt mỏi|mất ngủ|chán ăn|sút cân|giảm cân)\b", "Symptom"),
    (r"\b(đau họng|ngạt mũi|chảy mũi|hắt hơi)\b", "Symptom"),
    (r"\b(đau lưng|đau khớp|đau cơ)\b", "Symptom"),
    (r"\b(ngứa|phát ban|mẩn đỏ|sưng)\b", "Symptom"),
    (r"\b(rung tay|run chân)\b", "Symptom"),
    (r"\b(đi tiểu nhiều|đi tiểu buốt|đái dầm)\b", "Symptom"),
    (r"\b(đầy bụng|chướng bụng)\b", "Symptom"),
    (r"\b(đau mắt|nhìn mờ|chảy nước mắt)\b", "Symptom"),
    (r"\b(nghe kém|đau tai|chảy dịch tai)\b", "Symptom"),
    (r"\b(đau răng|chảy máu chân răng)\b", "Symptom"),
    (r"\b(khàn tiếng|khó nói)\b", "Symptom"),
    (r"\b(đau vùng thắt lưng|đau vùng thắt lưng)\b", "Symptom"),
    (r"\b(đau vùng bụng dưới|đau vùng bụng trên)\b", "Symptom"),
    (r"\b(đau vùng vai|đau vùng cổ)\b", "Symptom"),
    (r"\b(đau vùng hông|đau vùng mông)\b", "Symptom"),
    (r"\b(đau vùng bẹn|đau vùng háng)\b", "Symptom"),
    (r"\b(đau vùng đầu gối|đau vùng cổ chân)\b", "Symptom"),
    (r"\b(đau vùng cổ tay|đau vùng khuỷu tay)\b", "Symptom"),
    (r"\b(đau vùng bàn tay|đau vùng bàn chân)\b", "Symptom"),
    (r"\b(đau vùng ngón tay|đau vùng ngón chân)\b", "Symptom"),
    # Drugs - Thuốc
    (r"\b(metformin|insulin|glibenclamide|glimepiride|sitagliptin)\b", "Drug"),
    (r"\b(losartan|amlodipine|atenolol|bisoprolol|carvedilol)\b", "Drug"),
    (r"\b(aspirin|paracetamol|ibuprofen|naproxen|diclofenac)\b", "Drug"),
    (r"\b(thuốc\s+\w+|kháng sinh\s+\w+)\b", "Drug"),
    (r"\b(amoxicillin|azithromycin|cefuroxime|levofloxacin)\b", "Drug"),
    (r"\b(omeprazole|esomeprazole|pantoprazole|ranitidine)\b", "Drug"),
    (r"\b(amlodipine|nifedipine|diltiazem|verapamil)\b", "Drug"),
    (r"\b(simvastatin|atorvastatin|rosuvastatin)\b", "Drug"),
    (r"\b(captopril|enalapril|lisinopril|ramipril)\b", "Drug"),
    (r"\b(furosemide|spironolactone|hydrochlorothiazide)\b", "Drug"),
    (r"\b(clopidogrel|ticagrelor|prasugrel)\b", "Drug"),
    (r"\b(diazepam|alprazolam|lorazepam)\b", "Drug"),
    (r"\b(sertraline|fluoxetine|paroxetine|citalopram)\b", "Drug"),
    (r"\b(penicillin|cephalexin|doxycycline|clindamycin)\b", "Drug"),
    (r"\b(prednisone|dexamethasone|hydrocortisone)\b", "Drug"),
    (r"\b(warfarin|heparin|rivaroxaban)\b", "Drug"),
    (r"\b(thyroxine|levothyroxine)\b", "Drug"),
    (r"\b(methotrexate|azathioprine)\b", "Drug"),
    (r"\b(gabapentin|pregabalin)\b", "Drug"),
    (r"\b(ciprofloxacin|ofloxacin|norfloxacin)\b", "Drug"),
    (r"\b(clarithromycin|erythromycin)\b", "Drug"),
    # Anatomy - Giải phẫu
    (r"\b(tim|gan|thận|phổi|dạ dày|ruột|não)\b", "Anatomy"),
    (r"\b(tim mạch|hệ tiêu hóa|hệ thần kinh)\b", "Anatomy"),
    (r"\b(tuyến giáp|tuyến tụy|tuyến thượng thận)\b", "Anatomy"),
    (r"\b(xương khớp|cột sống|đốt sống)\b", "Anatomy"),
    (r"\b(mạch máu|động mạch|tĩnh mạch)\b", "Anatomy"),
    (r"\b(bàng quang|tuyến tiền liệt|tử cung|buồng trứng)\b", "Anatomy"),
    (r"\b(tụy mật|tụy tạng|ruột thừa)\b", "Anatomy"),
    (r"\b(hạch bạch huyết|tiêm mạch)\b", "Anatomy"),
    # Tests - Xét nghiệm
    (r"\b(HbA1c|đường huyết|huyết áp|xét nghiệm\s+\w+)\b", "Test"),
    (r"\b(siêu âm|chụp X-quang|MRI|CT scan|PET scan)\b", "Test"),
    (r"\b(điện tâm đồ|ECG|EKG)\b", "Test"),
    (r"\b(điện não đồ|EEG)\b", "Test"),
    (r"\b(nội soi|nội soi dạ dày|nội soi đại tràng)\b", "Test"),
    (r"\b(sinh thiết|mẫu bệnh phẩm)\b", "Test"),
    (r"\b(chọc dò tủy sống|lumbar puncture)\b", "Test"),
    (r"\b(xét nghiệm máu|xét nghiệm nước tiểu)\b", "Test"),
    (r"\b(chụp cộng hưởng từ|chụp cắt lớp)\b", "Test"),
    # Treatments/Procedures - Điều trị
    (r"\b(phẫu thuật|mổ)\b", "Treatment"),
    (r"\b(hóa trị|xạ trị|điều trị đích)\b", "Treatment"),
    (r"\b(lọc máu|thận nhân tạo|dialysis)\b", "Treatment"),
    (r"\b(thuốc đặc trị|thuốc điều trị)\b", "Treatment"),
    (r"\b(vật lý trị liệu|rehabilitation)\b", "Treatment"),
    (r"\b(giải phẫu|phẫu thuật nội soi)\b", "Treatment"),
    (r"\b(cấy ghép|ghép tạng)\b", "Treatment"),
    (r"\b(thuốc giảm đau|thuốc kháng viêm)\b", "Treatment"),
    # Vital Signs - Dấu hiệu sinh tồn
    (r"\b(nhịp tim|tần số hô hấp|nhiệt độ)\b", "VitalSign"),
    (r"\b(spO2|bão hòa oxy)\b", "VitalSign"),
]

# Capitalized medical terms (cautious pattern)
_CAPITALIZED_PATTERN = re.compile(
    r"\b([A-ZĐ][a-zàáạãảâầấậẫẩăằắặẵẳèéẹẽẻêềếệễểìíịĩỉòóọõỏôồốộỗổơờớợỡởùúụũủưừứựữửỳýỵỹỷđ]+"
    r"(?:\s+(?:[A-ZĐ][a-zàáạãảâầấậẫẩăằắặẵẳèéẹẽẻêềếệễểìíịĩỉòóọõỏôồốộỗổơờớợỡởùúụũủưừứựữửỳýỵỹỷđ]+|[a-zàáạãảâầấậẫẩăằắặẵẳèéẹẽẻêềếệễểìíịĩỉòóọõỏôồốộỗổơờớợỡởùúụũủưừứựữửỳýỵỹỷđ]+))*)",
    re.UNICODE,
)


def _entity_id(name: str, typ: str) -> str:
    key = f"{typ.lower()}|{name.lower()}"
    return f"ent_{hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]}"


def _normalize_name(name: str) -> str:
    t = name.strip()
    t = re.sub(r"\s+", " ", t)
    return t.strip(" .,;:!?()[]{}\"'")


def extract_entities_regex(text: str) -> list[dict[str, Any]]:
    """Extract entities using regex patterns for high recall.

    Returns list of {"name", "type", "start", "end", "confidence"}
    """
    entities = []
    seen = set()  # (start, end) to avoid duplicates

    # Pattern-based extraction
    for pattern, typ in MEDICAL_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            key = (match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            name = _normalize_name(match.group())
            if len(name) > 2:
                entities.append({
                    "name": name,
                    "type": typ,
                    "start": match.start(),
                    "end": match.end(),
                    "confidence": 0.7,
                    "source": "regex",
                })

    # Capitalized terms (cautious - might catch some false positives)
    for match in _CAPITALIZED_PATTERN.finditer(text):
        key = (match.start(), match.end())
        if key in seen:
            continue
        term = _normalize_name(match.group())
        # Filter out common non-medical capitalized words
        if len(term) > 3 and term.lower() not in {
            "bệnh", "thuốc", "người", "bác sĩ", "bệnh nhân",
            "hôm nay", "ngày mai", "năm nay", "việt nam",
        }:
            seen.add(key)
            entities.append({
                "name": term,
                "type": "Other",
                "start": match.start(),
                "end": match.end(),
                "confidence": 0.5,
                "source": "capitalized",
            })

    return entities


def to_records_regex(chunk_id: str, text: str) -> tuple[list[EntityRecord], list[MentionRecord]]:
    """Convert regex-extracted entities to KG records."""
    extracted = extract_entities_regex(text)
    entities = []
    mentions = []
    seen_ids = set()

    for e in extracted:
        name = e["name"]
        typ = e["type"]
        eid = _entity_id(name, typ)

        if eid not in seen_ids:
            seen_ids.add(eid)
            entities.append(EntityRecord(
                entity_id=eid,
                canonical_name=name,
                type=typ,
                aliases=[],
            ))

        mentions.append(MentionRecord(
            chunk_id=chunk_id,
            entity_id=eid,
            confidence=e["confidence"],
            start_char=e["start"],
            end_char=e["end"],
        ))

    return entities, mentions
