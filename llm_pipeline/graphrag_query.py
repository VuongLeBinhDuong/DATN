"""Chạy Microsoft GraphRAG CLI trên ``graphrag/`` hoặc truy vấn Neo4j khi bật trong config."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

# repo_root defined locally to avoid rag_milvus dependency
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

from llm_pipeline.neo4j_graphrag import (
    load_neo4j_config,
    neo4j_enabled,
    retrieve_graph_context,
    retrieve_graph_context_with_sources,
    synthesize_graph_answer,
)
from llm_pipeline.terminal_logging import configure_package_terminal_logging

# Custom KG routing (your 123k entities, 987k relations)
# from retrieval.graph_first import graph_first_retrieve, GraphFirstResult
from kg.neo4j_client import Neo4jKGClient

logger = logging.getLogger(__name__)


def _want_graphrag_terminal_log() -> bool:
    v = os.getenv("AGENT_TRACE", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True



def _custom_kg_available() -> bool:
    """Check if custom KG (your 123k entities) is available in Neo4j."""
    try:
        # Load Neo4j config from file (giống như neo4j_graphrag)
        neo_cfg = load_neo4j_config()
        if not neo_cfg or not neo4j_enabled(neo_cfg):
            if _want_graphrag_terminal_log():
                logger.warning("_custom_kg_available: Neo4j not configured")
            return False
        
        # Import Neo4j driver
        try:
            from neo4j import GraphDatabase
        except ImportError:
            if _want_graphrag_terminal_log():
                logger.warning("_custom_kg_available: neo4j driver not installed")
            return False
        
        uri = neo_cfg.get("uri")
        user = neo_cfg.get("user")
        password = neo_cfg.get("password")
        database = neo_cfg.get("database") or "neo4j"
        
        if not uri or not user or password is None:
            if _want_graphrag_terminal_log():
                logger.warning("_custom_kg_available: missing Neo4j credentials")
            return False
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            with driver.session(database=database) as session:
                result = session.run("MATCH (e:Entity) RETURN count(e) AS n").single()
                count = int(result["n"]) if result else 0
                if _want_graphrag_terminal_log():
                    logger.info("_custom_kg_available: found %s entities in custom KG", count)
                return count > 0
        finally:
            driver.close()
    except Exception as e:
        if _want_graphrag_terminal_log():
            logger.warning("_custom_kg_available: error checking custom KG: %s", e)
        return False


def _run_custom_kg_query(question: str, neo_cfg: dict[str, Any] | None = None) -> tuple[str, list[dict[str, Any]]]:
    """Run query using custom KG (graph-first retrieval)."""
    from retrieval.graph_first import graph_first_retrieve
    # Create client with config to ensure it works in web server
    client = Neo4jKGClient(cfg=neo_cfg) if neo_cfg else Neo4jKGClient()
    
    # Read dynamic parameters from Neo4j config (defaults to 8 seeds and 2 hops for better recall)
    top_seeds = 8
    hops = 2
    if neo_cfg:
        top_seeds = neo_cfg.get("top_k_nodes", top_seeds)
        hops = neo_cfg.get("neighbor_hops", hops)
        
    result = graph_first_retrieve(question, client=client, top_seed_entities=top_seeds, hops=hops)
    
    # Debug logging
    if _want_graphrag_terminal_log():
        logger.info(
            "_run_custom_kg_query: question=%r, chunks=%s, entities=%s, edges=%s",
            question[:100],
            len(result.evidence_chunks or []),
            len(result.subgraph.get("entities", [])),
            len(result.subgraph.get("edges", []))
        )
    
    # Format evidence into context string
    chunks = result.evidence_chunks or []
    lines: list[str] = []
    hits: list[dict[str, Any]] = []
    
    for i, ch in enumerate(chunks, 1):
        text = ch.get("text", "")
        chunk_id = ch.get("chunk_id", "")
        doc_id = ch.get("doc_id", "")
        lines.append(f"[{i}] chunk_id={chunk_id}, doc={doc_id}:\n{text}\n")
        hits.append({
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "title": ch.get("section_path", ""),
            "score": ch.get("mention_confidence", 0.0),
        })
    
    ctx = "\n".join(lines).strip()
    
    # Add subgraph info
    subgraph = result.subgraph or {}
    entities = subgraph.get("entities", [])
    edges = subgraph.get("edges", [])
    
    if entities:
        seed_set = set(result.debug.get("seed_entity_ids", []))
        for i, ent in enumerate(entities[:100]):
            pid = ent.get("entity_id", "")
            title = ent.get("canonical_name", pid)
            typ = ent.get("type", "Entity")
            aliases = ent.get("aliases", [])
            desc = f"Aliases: {', '.join(aliases)}" if aliases else f"Custom KG entity: {title}"
            
            score = 2.000 if pid in seed_set else 1.000
            ctx += f"\n\n--- Entity [{i + 1}] (score≈{score:.3f}) id={pid} ---"
            ctx += f"\ntitle: {title}"
            ctx += f"\ntype: {typ}"
            ctx += f"\ndescription: {desc}"
            
        if edges:
            ctx += "\n\n--- Quan hệ (trong tập trên) ---"
            for edge in edges[:40]:
                at = edge.get("subject_entity_id", "")
                bt = edge.get("object_entity_id", "")
                pred = edge.get("predicate", "RELATED")
                ctx += f"\n  • {at} —[{pred}]→ {bt}"
    
    return ctx, hits


def run_graphrag_query_with_sources(
    question: str, *, retrieval_query: str | None = None, return_raw_context: bool = False
) -> tuple[str, list[dict[str, Any]]] | tuple[str, list[dict[str, Any]], str]:
    """Route query exclusively to Custom KG, bypassing Microsoft GraphRAG entirely."""
    configure_package_terminal_logging()
    q = (question or "").strip()
    rq = (retrieval_query or q).strip() or q
    if _want_graphrag_terminal_log():
        logger.info(
            "graphrag_query: tổng hợp=%r | chỉ mục=%r",
            (q[:280] + "…") if len(q) > 280 else q,
            (rq[:280] + "…") if len(rq) > 280 else rq,
        )
    
    neo_cfg = load_neo4j_config()
    if _custom_kg_available():
        if _want_graphrag_terminal_log():
            logger.info("graphrag_query: routing to CUSTOM KG (graph-first)")
        ctx, hits = _run_custom_kg_query(rq, neo_cfg=neo_cfg)
        if ctx.strip():
            if neo_cfg and neo_cfg.get("synthesize_with_ollama", True):
                try:
                    ans = synthesize_graph_answer(q, ctx, neo_cfg)
                    if return_raw_context:
                        return ans, hits, ctx
                    return ans, hits
                except Exception as exc:
                    ans = f"Custom KG (không gọi được LLM: {exc}):\n\n{ctx}"
                    if return_raw_context:
                        return ans, hits, ctx
                    return ans, hits
            if return_raw_context:
                return ctx, hits, ctx
            return ctx, hits
        if return_raw_context:
            return "Custom KG không tìm thấy ngữ cảnh phù hợp cho câu hỏi này.", [], ""
        return "Custom KG không tìm thấy ngữ cảnh phù hợp cho câu hỏi này.", []
    
    msg = (
        "Custom KG (Cơ sở dữ liệu đồ thị tùy chỉnh) hiện tại không khả dụng hoặc chưa được cấu hình. "
        "Vui lòng kiểm tra kết nối Neo4j trong cấu hình hệ thống."
    )
    if return_raw_context:
        return msg, [], ""
    return msg, []



def run_graphrag_query(question: str, *, retrieval_query: str | None = None) -> str:
    """
    Mặc định: ``python -m graphrag query -r <repo>/graphrag -d <data_dir> "<question>"``.

    Nếu ``config/neo4j.json`` có ``enabled: true`` và ``query_backend: neo4j``:
    truy vấn đồ thị đã import (``scripts/graphrag_parquet_to_neo4j.py``), tùy chọn tổng hợp bằng Ollama.
    Để dùng lại CLI GraphRAG: đặt ``enabled: false`` hoặc ``query_backend: cli`` trong ``neo4j.json``.

    ``retrieval_query``: nếu set, dùng cho fulltext Neo4j (và lệnh CLI), còn ``question`` dùng trong prompt tổng hợp Ollama.
    Giúp khớp corpus QA khi agent paraphrase Action Input: ghép thêm câu gốc người dùng vào truy vấn chỉ mục.
    """
    return run_graphrag_query_with_sources(question, retrieval_query=retrieval_query)[0]
