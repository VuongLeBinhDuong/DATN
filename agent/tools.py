"""Tools: hàm được pipeline gọi **sau** khi router chọn nhánh ``graphrag`` (tương tự một branch/tool trong agent NeMo)."""

from __future__ import annotations

from typing import Any

from llm_pipeline.graphrag_query import run_graphrag_query


def expand_query_with_llm(question: str, num_variations: int = 3) -> list[str]:
    """Query Expansion: Dùng LLM tạo biến thể mở rộng để tìm kiếm đầy đủ hơn.
    
    Args:
        question: Câu hỏi gốc của người dùng
        num_variations: Số biến thể cần tạo (default: 3)
    
    Returns:
        List các query biến thể (bao gồm cả query gốc)
    
    Example:
        Input: "sốt cao"
        Output: ["sốt cao", "sốt cao nguyên nhân", "sốt trên 38 độ điều trị", "hạ sốt paracetamol liều"]
    """
    import json
    import os
    
    # Nếu query đã dài (>10 từ), không cần expand
    if len(question.split()) > 10:
        return [question]
    
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    
    prompt = f"""Bạn là trợ lý y khoa. Từ câu hỏi ngắn sau, hãy tạo {num_variations} biến thể mở rộng để tìm kiếm thông tin đầy đủ hơn.

Câu hỏi gốc: "{question}"

Yêu cầu:
- Mỗi biến thể thêm từ khóa y khoa liên quan
- Giữ nguyên ý chính của câu hỏi
- Trả về dạng JSON array

Ví dụ:
Input: "sốt cao"
Output: ["sốt cao nguyên nhân", "sốt trên 38 độ điều trị", "hạ sốt paracetamol liều"]

Chỉ trả về JSON array, không giải thích:"""

    try:
        import requests
        resp = requests.post(
            f"{host}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 200}
            },
            timeout=30
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content", "")
        
        # Extract JSON array from response
        content = content.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        
        variations = json.loads(content.strip())
        if isinstance(variations, list):
            # Thêm query gốc vào đầu
            result = [question] + [v for v in variations if v != question][:num_variations]
            return result[:num_variations + 1]
    except Exception:
        pass
    
    # Fallback: return original query
    return [question]


def tool_graphrag_query(question: str, *, retrieval_query: str | None = None, use_expansion: bool = True) -> str:
    """Công cụ tra kho GraphRAG — chỉ chạy khi kế hoạch điều phối bật ``use_graphrag``.
    
    Args:
        question: Câu hỏi cần tìm kiếm
        retrieval_query: Query tùy chỉnh (optional)
        use_expansion: Bật query expansion để tìm kiếm đa biến thể
    """
    if not use_expansion:
        return run_graphrag_query(question, retrieval_query=retrieval_query)
    
    # Query Expansion: tìm với nhiều biến thể và merge kết quả
    variations = expand_query_with_llm(question)
    all_hits: list[dict[str, Any]] = []
    
    for var in variations:
        result_text = run_graphrag_query(var, retrieval_query=retrieval_query)
        # Giả sử run_graphrag_query trả về text, cần parse thêm nếu cần hits
        # Tạm thời concat text results
        if result_text.strip():
            all_hits.append({"query": var, "text": result_text})
    
    # Merge và deduplicate theo nội dung
    seen_texts = set()
    merged_parts = []
    for hit in all_hits:
        text_snippet = hit["text"][:200]  # Dùng 200 chars để dedup
        if text_snippet not in seen_texts:
            seen_texts.add(text_snippet)
            merged_parts.append(f"--- Từ tìm kiếm: {hit['query']} ---\n{hit['text']}")
    
    return "\n\n".join(merged_parts) if merged_parts else run_graphrag_query(question, retrieval_query=retrieval_query)


def tool_pill_image_lookup(query: str) -> str:
    """Tra cứu ảnh thuốc đã crawl (labels.jsonl) — văn bản cho Observation."""
    from medical_records.pill_image_store import format_pill_image_observation, lookup_pill_images

    items = lookup_pill_images((query or "").strip(), limit=8)
    return format_pill_image_observation(items)


def pill_image_lookup_with_urls(query: str, *, limit: int = 8) -> tuple[str, list[str]]:
    """Cùng nội dung Observation + danh sách URL ảnh cho UI (``drug_images``)."""
    from medical_records.pill_image_store import format_pill_image_observation, lookup_pill_images

    items = lookup_pill_images((query or "").strip(), limit=limit)
    text = format_pill_image_observation(items)
    urls = [str(i["image_url"]) for i in items if i.get("image_url")]
    return text, urls


def try_auto_pill_images_for_question(question: str) -> tuple[str, list[str]]:
    """
    Chỉ tra ảnh khi câu có alias thuốc đã map (vd. paracetamol→acetaminophen) — tránh tra theo cả đoạn văn dài.
    Trả về (văn bản observation, urls) giống ``pill_image_lookup_with_urls``.
    """
    from medical_records.pill_image_store import resolve_pill_lookup_query

    rq = resolve_pill_lookup_query(question or "")
    if not rq:
        return "", []
    return pill_image_lookup_with_urls(rq, limit=8)


def merge_context_blocks(graphrag_text: str) -> str:
    """Single blob for RAG+LLM user message (see llm_pipeline.rag_llm)."""
    if graphrag_text.strip():
        return "--- GraphRAG (graph / global retrieval) ---\n" + graphrag_text.strip()
    return "(No retrieval context available.)"


def merge_retrieval_hits(existing: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gộp nguồn từ nhiều lần gọi graphrag_query; giữ điểm cao hơn khi trùng title+source."""

    def key(h: dict[str, Any]) -> tuple[str, str]:
        return (str(h.get("title") or ""), str(h.get("source") or ""))

    merged: dict[tuple[str, str], dict[str, Any]] = {key(h): dict(h) for h in existing}
    for h in new:
        k = key(h)
        old = merged.get(k)
        try:
            nsv = float(h["score"]) if h.get("score") is not None else None
            osv = float(old["score"]) if old and old.get("score") is not None else None
        except (TypeError, ValueError):
            nsv, osv = None, None
        if old is None or (nsv is not None and (osv is None or nsv > osv)):
            merged[k] = dict(h)
    return list(merged.values())


def augment_sources_for_ui(hits: list[dict[str, Any]], graph_text: str) -> list[dict[str, Any]]:
    """
    `hits` chỉ có khi tra thuốc từ URL trong ngữ cảnh GraphRAG. Nếu có ngữ cảnh
    nhưng không có hit, thêm một dòng để UI không hiểu nhầm là "không có nguồn".
    """
    out: list[dict[str, Any]] = [dict(h) for h in hits]
    if not out and (graph_text or "").strip():
        out.append(
            {
                "title": "Ngữ cảnh GraphRAG (kho tri thức đồ thị)",
                "link": "",
                "source": "graphrag_query",
                "score": None,
            }
        )
    return out
