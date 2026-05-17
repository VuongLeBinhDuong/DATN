"""Chạy Microsoft GraphRAG CLI trên ``graphrag/`` hoặc truy vấn Neo4j khi bật trong config."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
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
from retrieval.graph_first import graph_first_retrieve, GraphFirstResult
from kg.neo4j_client import Neo4jKGClient

logger = logging.getLogger(__name__)


def _want_graphrag_terminal_log() -> bool:
    v = os.getenv("AGENT_TRACE", "").strip().lower()
    if v in ("0", "false", "no", "off"):
        return False
    return True


def _resolve_graphrag_data_dir(graphrag_root: Path) -> Path | None:
    """Thư mục chứa entities.parquet (sau index hoặc update). Ưu tiên update_output rồi output."""
    for name in ("update_output", "output"):
        d = graphrag_root / name
        if (d / "entities.parquet").is_file():
            return d
    return None


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
    # Create client with config to ensure it works in web server
    client = Neo4jKGClient(cfg=neo_cfg) if neo_cfg else Neo4jKGClient()
    result = graph_first_retrieve(question, client=client)
    
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
        ctx += f"\n\n[Thông tin đồ thị: {len(entities)} entities, {len(edges)} relations]"
    
    return ctx, hits


def run_graphrag_query_with_sources(
    question: str, *, retrieval_query: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """Route query to: Custom KG -> Microsoft GraphRAG Neo4j -> CLI GraphRAG."""
    configure_package_terminal_logging()
    q = (question or "").strip()
    rq = (retrieval_query or q).strip() or q
    if _want_graphrag_terminal_log():
        logger.info(
            "graphrag_query: tổng hợp=%r | chỉ mục=%r",
            (q[:280] + "…") if len(q) > 280 else q,
            (rq[:280] + "…") if len(rq) > 280 else rq,
        )
    
    # === PRIORITY 1: Custom KG (your 123k entities) ===
    neo_cfg = load_neo4j_config()
    if _custom_kg_available():
        if _want_graphrag_terminal_log():
            logger.info("graphrag_query: routing to CUSTOM KG (graph-first)")
        ctx, hits = _run_custom_kg_query(rq, neo_cfg=neo_cfg)
        if ctx.strip():
            if neo_cfg and neo_cfg.get("synthesize_with_ollama", True):
                try:
                    return synthesize_graph_answer(q, ctx, neo_cfg), hits
                except Exception as exc:
                    return f"Custom KG (không gọi được LLM: {exc}):\n\n{ctx}", hits
            return ctx, hits
        # Custom KG empty, fall through to Microsoft GraphRAG
    
    # === PRIORITY 2: Microsoft GraphRAG Neo4j ===
    if neo4j_enabled(neo_cfg) and neo_cfg is not None:
        if _want_graphrag_terminal_log():
            logger.info("graphrag_query: routing to Microsoft GraphRAG Neo4j")
        ctx, hits = retrieve_graph_context_with_sources(rq, neo_cfg)
        if _want_graphrag_terminal_log():
            logger.info(
                "graphrag_query: Neo4j context=%s ký tự, hits=%s, synthesize=%s",
                len(ctx),
                len(hits),
                neo_cfg.get("synthesize_with_ollama", True),
            )
        if not ctx.strip():
            return (
                (
                    "Neo4j GraphRAG: không lấy được ngữ cảnh (thường do DB chưa có nút :GraphEntity, "
                    "sai database/URI so với config, hoặc fulltext index chưa tạo).\n\n"
                    "Làm lần lượt:\n"
                    "1) Đảm bảo đã có parquet nguồn (vd: backups/<snapshot>/graphrag_output hoặc graphrag/update_output).\n"
                    "2) Import vào đúng Neo4j trong config/neo4j.json (uri, database, password):\n"
                    "   • PowerShell (từ thư mục repo): .\\run_pipeline.ps1 -SyncGraphragToNeo4j\n"
                    "   • Hoặc: python scripts/graphrag_parquet_to_neo4j.py --output-dir backups\\<snapshot>\\graphrag_output --clear\n"
                    "     (thay <snapshot> bằng tên thật, ví dụ pre_reindex_20260408_210120).\n"
                    "3) Script import sẽ tạo fulltext index graphEntityFulltext (và community nếu có). Khởi động lại API sau khi import."
                ),
                [],
            )
        if neo_cfg.get("synthesize_with_ollama", True):
            try:
                return synthesize_graph_answer(q, ctx, neo_cfg), hits
            except Exception as exc:  # noqa: BLE001
                return (
                    f"Neo4j (không gọi được LLM tổng hợp: {exc}). Ngữ cảnh đã truy vấn:\n\n{ctx}",
                    hits,
                )
        return ctx, hits

    # === FALLBACK: CLI GraphRAG (không có structured hits) ===
    if _want_graphrag_terminal_log():
        logger.info("graphrag_query: routing to CLI GraphRAG")
    text = _run_graphrag_query_cli_only(rq)
    return text, []


def _run_graphrag_query_cli_only(rq: str) -> str:
    """Luồng GraphRAG CLI (không Neo4j)."""
    root = _repo_root()
    graphrag_root = root / "graphrag"
    if not graphrag_root.is_dir():
        return "GraphRAG: folder 'graphrag/' not found at repository root."

    data_dir = _resolve_graphrag_data_dir(graphrag_root)
    if data_dir is None:
        return (
            "GraphRAG: chua tim thay index (khong co entities.parquet trong graphrag/update_output hoac graphrag/output). "
            "Chay index hoac update, vi du: python -m graphrag index -r graphrag -m standard"
        )

    if _want_graphrag_terminal_log():
        logger.info("graphrag_query: GraphRAG CLI, data_dir=%s", data_dir)

    cmd = [
        sys.executable,
        "-m",
        "graphrag",
        "query",
        "-r",
        str(graphrag_root),
        "-d",
        str(data_dir),
        rq,
    ]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    proc = subprocess.run(cmd, check=False, capture_output=True, text=False, env=env)
    out = (proc.stdout or b"").decode("utf-8", errors="replace")
    err = (proc.stderr or b"").decode("utf-8", errors="replace")
    if proc.returncode == 0:
        text = out.strip() or "(GraphRAG returned empty output.)"
        if _want_graphrag_terminal_log():
            logger.info("graphrag_query: CLI trả về %s ký tự", len(text))
        return text

    stderr = (err or "").strip()
    stdout_tail = (out or "").strip()
    hint = ""
    if "No module named graphrag" in stderr:
        hint = "\nGợi ý: cài graphrag trong đúng venv đang chạy server (`pip install graphrag`)."

    last_exit = proc.returncode
    report = stderr or stdout_tail

    exe = shutil.which("graphrag")
    if exe:
        proc2 = subprocess.run(
            [exe, "query", "-r", str(graphrag_root), "-d", str(data_dir), rq],
            check=False,
            capture_output=True,
            text=False,
            env=env,
        )
        out2 = (proc2.stdout or b"").decode("utf-8", errors="replace")
        err2 = (proc2.stderr or b"").decode("utf-8", errors="replace")
        if proc2.returncode == 0:
            text2 = out2.strip() or "(GraphRAG returned empty output.)"
            if _want_graphrag_terminal_log():
                logger.info("graphrag_query: CLI (graphrag.exe) trả về %s ký tự", len(text2))
            return text2
        last_exit = proc2.returncode
        combined2 = (err2 or "").strip() or (out2 or "").strip()
        if combined2:
            report = combined2

    return f"GraphRAG query failed (exit {last_exit}):\n{report}{hint}"


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
