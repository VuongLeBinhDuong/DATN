"""Độ tin cậy truy hồi đơn giản cho UI (cao / trung / thấp)."""

from __future__ import annotations

from typing import Any, Literal

Level = Literal["cao", "trung", "thap"]


def compute_retrieval_confidence(
    sources: list[dict[str, Any]],
    graph_text: str,
) -> dict[str, Any]:
    """
    Heuristic dựa trên:
    - độ dài ngữ cảnh GraphRAG/Neo4j
    - điểm fulltext Lucene (thường >1 khi khớp tốt) vs điểm láng giềng (0.25–0.4)
    - có ít nhất một URL trích dẫn (hiếm với GraphEntity, nhưng giữ cho tương lai / Milvus)
    """
    ctx = (str(graph_text) if graph_text is not None else "").strip()
    ctx_len = len(ctx)
    scores: list[float] = []
    for s in sources:
        v = s.get("score")
        if v is None:
            continue
        try:
            scores.append(float(v))
        except (TypeError, ValueError):
            continue
    mx = max(scores) if scores else None
    n = len(scores)
    has_link = any(bool(str(s.get("link") or "").strip()) for s in sources)

    # Chỉ placeholder GraphRAG (không có điểm entity) nhưng có ngữ cảnh dài → trung
    if ctx_len < 120 and n == 0:
        level: Level = "thap"
        label = "Độ khớp nguồn: thấp — ít hoặc không có ngữ cảnh truy hồi."
    elif mx is not None and mx >= 1.0:
        level = "cao"
        label = "Độ khớp nguồn: cao — khớp chỉ mục fulltext tốt (điểm cao)."
    elif mx is not None and (mx >= 0.35 and n >= 3):
        level = "cao"
        label = "Độ khớp nguồn: cao — nhiều nút liên quan (fulltext + láng giềng)."
    elif ctx_len >= 800 and n >= 1:
        level = "trung"
        label = "Độ khớp nguồn: trung bình — có ngữ cảnh đủ dài; kiểm tra nguồn bên dưới."
    elif mx is not None and mx >= 0.25:
        level = "trung"
        label = "Độ khớp nguồn: trung bình — chủ yếu nút láng giềng / cộng đồng."
    elif ctx_len >= 200:
        level = "trung"
        label = "Độ khớp nguồn: trung bình — có ngữ cảnh; điểm khớp không cao."
    else:
        level = "thap"
        label = "Độ khớp nguồn: thấp — ngữ cảnh ngắn hoặc trùng khớp yếu."

    if has_link and level == "trung":
        level = "cao"
        label = "Độ khớp nguồn: cao — có liên kết trích dẫn trực tiếp."

    return {
        "level": level,
        "label_vi": label,
        "max_score": mx,
        "n_scored_sources": n,
        "context_chars": ctx_len,
        "has_link": has_link,
    }
