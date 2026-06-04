from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from kg.neo4j_client import Neo4jKGClient
from llm_pipeline.llm_chat import chat_ollama, chat_openrouter, synthesis_backend


def _fulltext_safe_query(q: str) -> str:
    t = (q or "").strip()
    if not t:
        return "*"
    t = re.sub(r'[~^*+\-:"]', " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    cap = max(128, min(int(os.getenv("KG_FULLTEXT_QUERY_MAX_CHARS", "512")), 2048))
    return t[:cap] if t else "*"


def _tokenize(s: str) -> set[str]:
    t = (s or "").lower()
    t = re.sub(r"[^0-9a-zA-Zà-ỹÀ-Ỹ]+", " ", t)
    toks = {x for x in t.split() if 2 <= len(x) <= 40}
    return toks


def _score_overlap(question: str, chunk_text: str) -> float:
    q = _tokenize(question)
    c = _tokenize(chunk_text)
    if not q or not c:
        return 0.0
    inter = len(q & c)
    return inter / max(1.0, len(q) ** 0.5)


def _llm_rerank(question: str, chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    # Lightweight rerank: ask LLM to pick best chunk_ids.
    items = []
    for i, ch in enumerate(chunks[: min(len(chunks), 20)]):
        items.append(
            f"[{i+1}] chunk_id={ch['chunk_id']}\n{(ch.get('text') or '')[:800]}\n"
        )
    prompt = (
        "Bạn là hệ thống rerank evidence cho RAG.\n"
        "Chọn các chunk liên quan nhất để trả lời câu hỏi. "
        f"Trả về DUY NHẤT JSON array các chunk_id (tối đa {top_k}).\n\n"
        f"QUESTION:\n{question}\n\n"
        "CHUNKS:\n" + "\n".join(items)
    )

    host = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
    timeout = int(os.getenv("OLLAMA_TIMEOUT") or "120")
    temperature = float(os.getenv("KG_RERANK_TEMPERATURE") or "0.0")
    num_predict = int(os.getenv("KG_RERANK_NUM_PREDICT") or "512")

    backend = synthesis_backend()
    if backend == "openrouter":
        or_model = os.getenv("OPENROUTER_MODEL") or None
        raw = chat_openrouter(prompt, model=or_model, timeout=timeout, temperature=temperature, max_tokens=min(num_predict, 1024))
    else:
        raw = chat_ollama(
            prompt,
            host=host,
            model=model,
            timeout=timeout,
            temperature=temperature,
            num_predict=num_predict,
        )

    import json
    import re as _re

    t = (raw or "").strip()
    if t.startswith("```"):
        t = _re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = _re.sub(r"\s*```$", "", t).strip()
    try:
        picked = json.loads(t)
    except Exception:
        picked = []
    if not isinstance(picked, list):
        picked = []
    picked_ids = {str(x) for x in picked if str(x).strip()}
    if not picked_ids:
        return chunks[:top_k]
    order = {cid: i for i, cid in enumerate(picked_ids)}
    return sorted([c for c in chunks if c["chunk_id"] in picked_ids], key=lambda c: order.get(c["chunk_id"], 10**9))[:top_k]


def reciprocal_rank_fusion(
    graph_ranked: list[dict[str, Any]],
    lexical_ranked: list[dict[str, Any]],
    k: int = 60,
) -> list[dict[str, Any]]:
    """Fuse multiple query rank paths using Reciprocal Rank Fusion (RRF)."""
    scores: dict[str, float] = {}
    chunk_map: dict[str, dict[str, Any]] = {}
    
    for idx, ch in enumerate(graph_ranked):
        cid = ch.get("chunk_id")
        if cid:
            chunk_map[cid] = ch
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + idx + 1)
            
    for idx, ch in enumerate(lexical_ranked):
        cid = ch.get("chunk_id")
        if cid:
            chunk_map[cid] = ch
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + idx + 1)
            
    sorted_cids = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)
    return [chunk_map[cid] for cid in sorted_cids]


def _cross_encoder_rerank(question: str, chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
    """Local neural cross-encoder reranker with graceful fallback to LLM/lexical ranking."""
    try:
        from sentence_transformers import CrossEncoder
        # Vietnamese document reranker or default lightweight cross-encoder
        model_name = os.getenv("KG_RERANKER_MODEL", "dangvantuan/vietnamese-document-reranker")
        model = CrossEncoder(model_name, max_length=512)
        
        pairs = [[question, (ch.get("text") or "")[:800]] for ch in chunks]
        scores = model.predict(pairs)
        
        for ch, score in zip(chunks, scores):
            ch["rerank_score"] = float(score)
            
        return sorted(chunks, key=lambda x: x.get("rerank_score", -9999.0), reverse=True)[:top_k]
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("CrossEncoder rerank failed, falling back to LLM rerank: %s", e)
        return _llm_rerank(question, chunks, top_k)


@dataclass(frozen=True)
class GraphFirstResult:
    evidence_chunks: list[dict[str, Any]]
    subgraph: dict[str, Any]
    debug: dict[str, Any]


def prune_subgraph(subgraph: dict[str, Any], seed_ids: list[str]) -> dict[str, Any]:
    """Clean and prune the retrieved subgraph to reduce noise and isolate connected clinical components.
    
    Filters out non-clinical terms, generic type labels, and isolated entity nodes (degree = 0).
    """
    entities = subgraph.get("entities") or []
    edges = subgraph.get("edges") or []
    
    # 1. Clean and filter entities
    clean_entities = []
    valid_entity_ids = set()
    seed_set = set(seed_ids)
    
    # Check for noisy/generic terms or isolated characters
    noise_pattern = re.compile(r"^[0-9\W_]+$")
    generic_types = {"other", "generic", "noise", "document", "chunk"}
    
    for ent in entities:
        ent_id = ent.get("entity_id")
        name = (ent.get("name") or "").strip()
        ent_type = (ent.get("type") or "").strip().lower()
        
        if not ent_id or not name:
            continue
        if len(name) < 2 or noise_pattern.match(name):
            continue
        if ent_type in generic_types:
            continue
            
        clean_entities.append(ent)
        valid_entity_ids.add(ent_id)
        
    # 2. Filter edges to only those connecting valid entities
    clean_edges = []
    connected_entity_ids = set()
    
    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        
        if source in valid_entity_ids and target in valid_entity_ids:
            clean_edges.append(edge)
            connected_entity_ids.add(source)
            connected_entity_ids.add(target)
            
    # 3. Soft Pruning of Isolated Nodes (degree = 0)
    # Keep an entity only if it is connected OR is a primary search seed
    pruned_entities = [
        ent for ent in clean_entities 
        if ent.get("entity_id") in connected_entity_ids or ent.get("entity_id") in seed_set
    ]
    
    return {
        "entities": pruned_entities,
        "edges": clean_edges
    }


def extract_clinical_entities(question: str) -> list[dict[str, str]]:
    """Extract clinical entities of types DRUG, DISEASE, SYMPTOM, TEST from the query.
    
    Uses the configured lightweight router model to ensure fast execution.
    """
    from core.settings import get_settings
    from core.llm_backends import OllamaBackend
    import json
    import re
    
    settings = get_settings()
    backend = OllamaBackend()
    if not backend.is_available():
        return []
        
    prompt = (
        "Bạn là một trợ lý y khoa AI chuyên nghiệp có nhiệm vụ trích xuất các thực thể lâm sàng từ câu hỏi của người dùng.\n"
        "Hãy trích xuất tất cả các thực thể thuộc một trong các loại sau:\n"
        "- DRUG: Tên thuốc, tên biệt dược hoặc hoạt chất (Ví dụ: Metformin, Aspirin, Paracetamol, kháng sinh).\n"
        "- DISEASE: Tên bệnh lý, hội chứng y khoa (Ví dụ: tiểu đường, suy thận, suy gan, huyết áp cao, gout).\n"
        "- SYMPTOM: Triệu chứng lâm sàng (Ví dụ: đau đầu, sốt, buồn nôn, ho).\n"
        "- TEST: Chỉ số hoặc xét nghiệm y tế (Ví dụ: glucose, chỉ số ALT, xét nghiệm máu, HbA1c).\n\n"
        "QUY TẮC:\n"
        "- Trả về kết quả dưới dạng một JSON array duy nhất, mỗi phần tử là một object có hai trường: \"name\" (tên thực thể được chuẩn hóa viết thường hoặc viết hoa chữ cái đầu phù hợp) và \"type\" (chỉ nhận một trong bốn giá trị: DRUG, DISEASE, SYMPTOM, TEST).\n"
        "- Không viết thêm bất kỳ lời giải thích nào khác ngoài JSON array đó.\n"
        "- Nếu không có thực thể nào, trả về: []\n\n"
        "Ví dụ:\n"
        "User: Bị tiểu đường uống Metformin và Aspirin cùng lúc được không?\n"
        '[{"name": "tiểu đường", "type": "DISEASE"}, {"name": "Metformin", "type": "DRUG"}, {"name": "Aspirin", "type": "DRUG"}]\n\n'
        f"Câu hỏi: {question}\n"
        "JSON:"
    )
    
    try:
        res = backend.chat(prompt=prompt, model=settings.ollama.router_model, temperature=0.0).strip()
        if res.startswith("```"):
            res = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", res)
            res = re.sub(r"\s*```$", "", res).strip()
        data = json.loads(res)
        if isinstance(data, list):
            return [{"name": str(x.get("name", "")), "type": str(x.get("type", "")).upper()} for x in data if x.get("name")]
    except Exception:
        pass
    return []


def graph_first_retrieve(
    question: str,
    *,
    client: Neo4jKGClient | None = None,
    top_seed_entities: int = 12,
    hops: int = 2,
    evidence_k: int = 8,
    extra_chunks_k: int = 20,
) -> GraphFirstResult:
    c = client or Neo4jKGClient()
    ft_q = _fulltext_safe_query(question)
    
    # 1. Try Clinical NER Extraction
    ner_entities = extract_clinical_entities(question)
    ner_entity_ids = []
    used_path_query = False
    
    if len(ner_entities) >= 2:
        for ent in ner_entities:
            matched = c.search_entities_fulltext(ent["name"], limit=1)
            if matched and matched[0].get("entity_id"):
                ner_entity_ids.append(matched[0]["entity_id"])
                
    # 2. Try Path Query between extracted entities
    if len(ner_entity_ids) >= 2:
        subgraph = c.find_paths_between_entities(ner_entity_ids, max_hops=hops)
        if subgraph.get("edges"):
            used_path_query = True
            seed_ids = list(ner_entity_ids)
            seeds = [{"entity_id": eid, "canonical_name": eid, "type": "NER_RESOLVED"} for eid in seed_ids]

    # Fallback to default k-hop expansion if path query is not applicable or found nothing
    if not used_path_query:
        seeds = c.search_entities_fulltext(ft_q, limit=top_seed_entities)
        seed_ids = [s["entity_id"] for s in seeds if s.get("entity_id")]
        subgraph = c.expand_subgraph(seed_ids, hops=hops)
    
    # Apply Clinical Graph Validation & Soft Pruning
    subgraph = prune_subgraph(subgraph, seed_ids)
    
    entities = subgraph.get("entities") or []
    if seed_ids and entities:
        seed_set = set(seed_ids)
        subgraph["entities"] = sorted(
            entities,
            key=lambda e: (e.get("entity_id") not in seed_set)
        )
    edges = subgraph.get("edges") or []

    evidence_ids: list[str] = []
    for e in edges:
        cid = e.get("evidence_chunk_id")
        if cid and cid not in evidence_ids:
            evidence_ids.append(cid)

    chunks_from_edges = c.fetch_chunks_by_ids(evidence_ids)

    # Add some chunks mentioning seed entities to improve recall when relations are sparse.
    mention_chunks = c.fetch_chunks_mentioning_entities(seed_ids, limit=extra_chunks_k)

    # Dedup by chunk_id
    merged: dict[str, dict[str, Any]] = {}
    for ch in chunks_from_edges + mention_chunks:
        cid = ch.get("chunk_id")
        if cid:
            merged[cid] = ch

    # 1. Graph-based candidate ranking (based on mention confidence)
    graph_ranked = sorted(
        merged.values(),
        key=lambda x: (float(x.get("mention_confidence") or 0.0)),
        reverse=True,
    )

    # 2. Lexical-based candidate ranking (based on term overlap)
    lexical_ranked = sorted(
        merged.values(),
        key=lambda x: (_score_overlap(question, x.get("text") or "")),
        reverse=True,
    )

    # 3. Reciprocal Rank Fusion (RRF)
    fused_ranked = reciprocal_rank_fusion(graph_ranked, lexical_ranked)

    # 4. Reranking Layer (Neural Cross-Encoder or LLM agent choice)
    use_reranker = (os.getenv("KG_USE_RERANKER") or "").strip().lower() in ("1", "true", "yes", "on", "active")
    use_llm_rerank = (os.getenv("KG_USE_LLM_RERANK") or "").strip().lower() in ("1", "true", "yes", "on")

    if fused_ranked:
        if use_reranker:
            candidates = fused_ranked[:20]
            top = _cross_encoder_rerank(question, candidates, top_k=evidence_k)
        elif use_llm_rerank:
            top = _llm_rerank(question, fused_ranked, top_k=evidence_k)
        else:
            top = fused_ranked[:evidence_k]
    else:
        top = []

    debug = {
        "fulltext_query": ft_q,
        "seed_entities": seeds,
        "seed_entity_ids": seed_ids,
        "hops": hops,
        "evidence_from_edges": len(chunks_from_edges),
        "evidence_from_mentions": len(mention_chunks),
        "use_rrf_fusion": True,
        "use_reranker": use_reranker,
        "use_llm_rerank": use_llm_rerank,
    }
    return GraphFirstResult(evidence_chunks=top, subgraph=subgraph, debug=debug)

