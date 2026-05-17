from __future__ import annotations

import re

# Minimal predicate taxonomy for relation normalization.
# Keep this intentionally small to reduce graph noise; expand as you collect eval errors.
CANONICAL_PREDICATES: tuple[str, ...] = (
    "IS_A",
    "PART_OF",
    "TREATS",
    "CAUSES",
    "ASSOCIATED_WITH",
    "INTERACTS_WITH",
    "CONTRAINDICATED_FOR",
    "SYMPTOM_OF",
    "DIAGNOSED_BY",
    "PREVENTS",
    "HAS_SIDE_EFFECT",
    "AFFECTS",
)


# Expanded alias mappings for better normalization
_ALIAS_TO_CANONICAL: list[tuple[re.Pattern[str], str]] = [
    # IS_A
    (re.compile(r"^(is a|type of|kind of|là|thuộc loại|là một|là loại)$", re.I), "IS_A"),
    # PART_OF
    (re.compile(r"^(part of|belongs to|thuộc|nằm trong|là phần của)$", re.I), "PART_OF"),
    # TREATS
    (re.compile(r"^(treats|điều trị|chữa|therapy for|treatment for|được điều trị bởi)$", re.I), "TREATS"),
    (re.compile(r"^(treated by|được chữa bằng|được điều trị bằng)$", re.I), "TREATED_BY"),
    # CAUSES
    (re.compile(r"^(causes|gây ra|dẫn đến|nguyên nhân|do|tạo ra)$", re.I), "CAUSES"),
    (re.compile(r"^(caused by|do đó|bởi vì|kết quả của)$", re.I), "CAUSES"),
    # ASSOCIATED_WITH
    (re.compile(r"^(associated with|liên quan|tương quan|có liên hệ|có liên quan)$", re.I), "ASSOCIATED_WITH"),
    (re.compile(r"^(related to|có liên quan đến|liên kết với|kết nối với)$", re.I), "ASSOCIATED_WITH"),
    # INTERACTS_WITH
    (re.compile(r"^(interacts with|tương tác|có tương tác|tương tác với)$", re.I), "INTERACTS_WITH"),
    # CONTRAINDICATED_FOR
    (re.compile(r"^(contraindicated for|chống chỉ định|không nên dùng|không dùng cho)$", re.I), "CONTRAINDICATED_FOR"),
    # SYMPTOM_OF
    (re.compile(r"^(symptom of|triệu chứng của|có triệu chứng|triệu chứng)$", re.I), "SYMPTOM_OF"),
    (re.compile(r"^(has symptom|có triệu chứng|biểu hiện)$", re.I), "SYMPTOM_OF"),
    # DIAGNOSED_BY
    (re.compile(r"^(diagnosed by|chẩn đoán bằng|xác định bởi|được chẩn đoán)$", re.I), "DIAGNOSED_BY"),
    # PREVENTS
    (re.compile(r"^(prevents|phòng ngừa|ngăn ngừa|tránh|phòng chống)$", re.I), "PREVENTS"),
    # HAS_SIDE_EFFECT
    (re.compile(r"^(has side effect|side effect|tác dụng phụ|có tác dụng phụ)$", re.I), "HAS_SIDE_EFFECT"),
    # AFFECTS
    (re.compile(r"^(affects|ảnh hưởng|tác động|có ảnh hưởng)$", re.I), "AFFECTS"),
]


def _fuzzy_match_predicate(raw: str, threshold: float = 85.0) -> str | None:
    """Try fuzzy matching against known aliases."""
    try:
        from rapidfuzz import fuzz
    except ImportError:
        return None
    
    normalized = re.sub(r"[_\-\s]+", " ", raw).strip().lower()
    
    # Build a list of all known patterns for fuzzy matching
    known_patterns = []
    for pat, canon in _ALIAS_TO_CANONICAL:
        # Extract the pattern string (simplified)
        pattern_str = pat.pattern.replace(r"^(", "").replace(")$", "").replace("|", " ")
        known_patterns.append((pattern_str.lower(), canon))
    
    # Find best match
    best_match = None
    best_score = 0
    
    for pattern_str, canon in known_patterns:
        score = fuzz.partial_ratio(normalized, pattern_str)
        if score > best_score and score >= threshold:
            best_score = score
            best_match = canon
    
    return best_match


def normalize_predicate(raw: str) -> str:
    """Normalize a raw predicate string to a canonical label.
    
    Steps:
    1. Exact match against canonical predicates
    2. Regex pattern match against known aliases
    3. Fuzzy matching (if rapidfuzz available)
    4. Fallback to RELATED_TO
    """
    t = (raw or "").strip()
    if not t:
        return "RELATED_TO"

    # Step 1: Exact match
    upper = re.sub(r"\s+", " ", t).strip().upper()
    if upper in CANONICAL_PREDICATES:
        return upper

    # Step 2: Regex pattern match
    compact = re.sub(r"[_\-\s]+", " ", t).strip()
    for pat, canon in _ALIAS_TO_CANONICAL:
        if pat.match(compact):
            return canon

    # Step 3: Fuzzy matching
    fuzzy_result = _fuzzy_match_predicate(compact)
    if fuzzy_result:
        return fuzzy_result

    # Step 4: Fallback
    return "RELATED_TO"

