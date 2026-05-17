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


@dataclass(frozen=True)
class GraphFirstResult:
    evidence_chunks: list[dict[str, Any]]
    subgraph: dict[str, Any]
    debug: dict[str, Any]


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
    seeds = c.search_entities_fulltext(ft_q, limit=top_seed_entities)
    seed_ids = [s["entity_id"] for s in seeds if s.get("entity_id")]

    subgraph = c.expand_subgraph(seed_ids, hops=hops)
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

    # Simple overlap ranking
    ranked = sorted(
        merged.values(),
        key=lambda x: (_score_overlap(question, x.get("text") or ""), float(x.get("mention_confidence") or 0.0)),
        reverse=True,
    )

    use_llm_rerank = (os.getenv("KG_USE_LLM_RERANK") or "").strip().lower() in ("1", "true", "yes", "on")
    if use_llm_rerank and ranked:
        top = _llm_rerank(question, ranked, top_k=evidence_k)
    else:
        top = ranked[:evidence_k]

    debug = {
        "fulltext_query": ft_q,
        "seed_entities": seeds,
        "seed_entity_ids": seed_ids,
        "hops": hops,
        "evidence_from_edges": len(chunks_from_edges),
        "evidence_from_mentions": len(mention_chunks),
        "use_llm_rerank": use_llm_rerank,
    }
    return GraphFirstResult(evidence_chunks=top, subgraph=subgraph, debug=debug)

