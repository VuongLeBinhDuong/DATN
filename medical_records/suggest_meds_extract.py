"""Trích tên thuốc từ đoạn gợi ý LLM (minh họa UI — không thay cơ sở kê đơn)."""

from __future__ import annotations

import re
from typing import Any

# Hoạt chất / tên thường gặp trong gợi ý tiếng Việt–Anh (mở rộng dần).
_DRUG_KNOWN = re.compile(
    r"(?i)\b("
    r"allopurinol|febuxostat|colchicine|metformin|glibenclamide|gliclazide|insulin|glargine|"
    r"atorvastatin|rosuvastatin|simvastatin|amlodipine|losartan|enalapril|ramipril|"
    r"omeprazole|pantoprazole|paracetamol|acetaminophen|ibuprofen|aspirin|acetylsalicylic|"
    r"furosemide|spironolactone|levothyroxine|warfarin|clopidogrel|"
    r"prednisolone|hydrocortisone|salbutamol|montelukast"
    r")\b"
)

_MAX_SNIPPET = 560


def _clean_snippet_text(s: str) -> str:
    t = s.replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"#{1,3}\s*", "", t)
    t = t.replace("**", "")
    t = re.sub(r"\s*\*\s*", " · ", t)
    return t.strip()


def _snippet_for_match(raw: str, m: re.Match) -> str:
    """Lấy đoạn quanh tên thuốc: ưu tiên từ đầu câu/đoạn tới trước mục ### tiếp theo."""
    a, b = m.start(), m.end()
    left = max(0, a - 280)
    head = raw[left:a]
    for sep in ("\n\n", "\n", ". ", ":", ";"):
        p = head.rfind(sep)
        if p != -1 and p > 20:
            left = left + p + len(sep)
            break

    right = min(len(raw), b + 480)
    tail = raw[b:right]
    for sep in ("\n\n###", "\n###", "\n\n"):
        p = tail.find(sep)
        if p != -1:
            right = b + p
            break

    chunk = raw[left:right]
    chunk = _clean_snippet_text(chunk)
    if len(chunk) > _MAX_SNIPPET:
        cut = chunk[: _MAX_SNIPPET - 1]
        if " " in cut:
            cut = cut.rsplit(" ", 1)[0]
        chunk = cut + "…"
    return chunk


def extract_suggested_drugs_from_narrative(text: str | None) -> list[dict[str, Any]]:
    """
    Trả về danh sách {name, snippet} để UI hiển thị thẻ; trùng tên chỉ giữ lần đầu.
    """
    if not text or not str(text).strip():
        return []
    raw = str(text)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for m in _DRUG_KNOWN.finditer(raw):
        name = m.group(1).strip()
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        snippet = _snippet_for_match(raw, m)
        display = name.title() if name.islower() else name
        out.append({"name": display, "snippet": snippet})
        if len(out) >= 16:
            break
    return out
