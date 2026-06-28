"""Truy vấn GraphRAG trên Neo4j (entity + community + quan hệ).

Lưu ý thiết kế (so với GraphRAG CLI gốc):

- **Community reasoning**: import `communities.parquet` + `community_reports.parquet` tạo
``(:Community)`` và ``(:GraphEntity)-[:IN_COMMUNITY]->(:Community)``; truy vấn kèm
``summary`` / ``level`` (phân cấp) — không chỉ fulltext trên entity.
- **Fulltext ≠ semantic**: chỉ mục từ khóa (Lucene). Bổ sung ngữ nghĩa có thể kết hợp với
embedding store khác ở tầng ứng dụng; repo này dùng Neo4j + GraphRAG làm luồng chính.
- **Độ trễ**: giữ ``neighbor_hops`` ∈ [0,2], ``top_k_nodes`` / ``top_communities`` nhỏ để giảm latency.

Schema: ``GraphEntity.id`` (UNIQUE), ``GraphEntity.graphrag_uuid``, ``Community.community_id`` (UNIQUE).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

from core.connection_pool import get_neo4j_driver
from llm_pipeline.llm_chat import chat_ollama, chat_openrouter, synthesis_backend
from llm_pipeline.rag_llm import DEFAULT_AGENT_MERGED_PROMPT, _rag_llm_user_message

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None  # type: ignore[misc, assignment]


def default_neo4j_config_path() -> Path:
    return _repo_root() / "config" / "neo4j.json"


def load_neo4j_config() -> dict[str, Any] | None:
    p = default_neo4j_config_path()
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def neo4j_enabled(cfg: dict[str, Any] | None) -> bool:
    if not cfg:
        return False
    if not bool(cfg.get("enabled")):
        return False
    backend = str(cfg.get("query_backend") or "").strip().lower()
    if backend in ("", "neo4j", "parquet_neo4j"):
        return True
    return False


def _fulltext_safe_query(q: str) -> str:
    t = (q or "").strip()
    if not t:
        return "*"
    t = re.sub(r'[~^*+\-:"]', " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    # Lucene fulltext: đoạn đầu câu hỏi quyết định trúng index; CLI parquet không bị giới hạn này.
    try:
        cap = int(os.getenv("NEO4J_FULLTEXT_QUERY_MAX_CHARS", "1024"))
    except ValueError:
        cap = 1024
    cap = max(256, min(cap, 4096))
    return t[:cap] if t else "*"


def _safe_index_name(name: str) -> str:
    s = "".join(c for c in (name or "") if c.isalnum() or c == "_")
    return s or "graphEntityFulltext"


def _normalize_bolt_uri(uri: str) -> str:
    try:
        p = urlparse((uri or "").strip())
        if p.scheme and p.hostname and p.hostname.lower() == "localhost":
            port = p.port or 7687
            return urlunparse((p.scheme, f"127.0.0.1:{port}", p.path or "", "", "", ""))
    except Exception:
        pass
    return uri


def _graph_entity_label_in_use(session: Any) -> bool:
    """
    Tránh chạy MATCH (n:GraphEntity) khi DB chưa import — Neo4j 5 hay cảnh báo
    'label does not exist' / 'property key does not exist' dù truy vấn vẫn chạy.
    """
    try:
        rec = session.run(
            "CALL db.labels() YIELD label AS l WHERE l = 'GraphEntity' RETURN l LIMIT 1"
        ).single()
        return rec is not None
    except Exception:
        return False


def retrieve_graph_context_with_sources(
    question: str,
    cfg: dict[str, Any],
) -> tuple[str, list[dict[str, Any]]]:
    """Redirect to Custom KG query (graph-first retrieval) to bypass Microsoft GraphRAG."""
    from llm_pipeline.graphrag_query import _run_custom_kg_query
    return _run_custom_kg_query(question, neo_cfg=cfg)


def retrieve_graph_context(question: str, cfg: dict[str, Any]) -> str:
    """Fulltext entity (+ tùy chọn community) + RELATED láng giềng; kèm community reports qua IN_COMMUNITY."""
    text, _ = retrieve_graph_context_with_sources(question, cfg)
    return text


def synthesize_graph_answer(
    question: str,
    graph_context: str,
    cfg: dict[str, Any],
) -> str:
    """Tổng hợp câu trả lời từ ngữ cảnh Neo4j (Ollama local hoặc OpenRouter khi có ``OPENROUTER_API_KEY``).

    Prompt mặc định trong ``<repo>/prompts`` (vd. ``agent_merged_context_prompt.txt``).
    Đổi bằng ``synthesis_prompt_basename`` / ``synthesis_prompt_relpath`` trong ``config/neo4j.json``.
    """
    basename = str(
        cfg.get("synthesis_prompt_basename") or os.getenv("NEO4J_SYNTHESIS_PROMPT_BASENAME") or ""
    ).strip()
    rel = str(cfg.get("synthesis_prompt_relpath") or os.getenv("NEO4J_SYNTHESIS_PROMPT_RELPATH") or "").strip()

    ctx_for_llm = (
        "--- Neo4j / GraphRAG (entities, communities, quan hệ) ---\n\n" + (graph_context or "").strip()
    )

    prompt: str
    if basename:
        try:
            prompt = _rag_llm_user_message(question, ctx_for_llm, prompt_basename=basename)
        except FileNotFoundError:
            return (
                f"Neo4j synthesis: không tìm thấy file prompt trong thư mục app prompts ({basename}). "
                "Mặc định là <repo>/prompts; có thể đặt LLM_APP_PROMPTS_DIR. "
                "Đặt synthesis_prompt_basename đúng tên file (vd. agent_merged_context_prompt.txt)."
            )
    elif rel:
        path = (_repo_root() / rel).resolve()
        if not path.is_file():
            return (
                f"Neo4j synthesis: không tìm thấy file: {path}. "
                "Kiểm tra synthesis_prompt_relpath trong config/neo4j.json."
            )
        template = path.read_text(encoding="utf-8")
        response_type = str(
            cfg.get("synthesis_response_type")
            or os.getenv("NEO4J_SYNTHESIS_RESPONSE_TYPE")
            or (
                "Vừa đủ ý, tiếng Việt; trích [Data: Sources (...)] khi có id trong ngữ cảnh; "
                "trả lời trực tiếp câu hỏi với nội dung cụ thể, không thay câu trả lời bằng lời bảo hỏi bác sĩ/chuyên gia."
            )
        ).strip()
        wrapped_ctx = (
            "--- User question ---\n\n"
            f"{question}\n\n"
            "--- Retrieved graph context (Neo4j / GraphRAG entities & communities) ---\n\n"
            f"{graph_context}"
        )
        try:
            if "{response_type}" in template:
                prompt = template.format(context_data=wrapped_ctx, response_type=response_type)
            else:
                prompt = template.format(context_data=wrapped_ctx)
        except KeyError as exc:
            return f"Neo4j synthesis: template thiếu placeholder {exc}."
    else:
        try:
            prompt = _rag_llm_user_message(
                question, ctx_for_llm, prompt_basename=DEFAULT_AGENT_MERGED_PROMPT
            )
        except FileNotFoundError as exc:
            return f"Neo4j synthesis: {exc}"

    host = (os.getenv("OLLAMA_HOST") or cfg.get("ollama_host") or "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL") or cfg.get("ollama_model") or "llama3.2:3b"
    _to = os.getenv("OLLAMA_TIMEOUT")
    try:
        timeout = int(_to) if _to not in (None, "") else int(cfg.get("ollama_timeout") or 120)
    except (TypeError, ValueError):
        timeout = 120
    _t_raw = cfg.get("synthesis_temperature")
    if _t_raw is None:
        _t_raw = os.getenv("NEO4J_SYNTHESIS_TEMPERATURE")
    try:
        temp = float(_t_raw) if _t_raw is not None and str(_t_raw).strip() != "" else 0.2
    except (TypeError, ValueError):
        temp = 0.2

    _np_raw = cfg.get("synthesis_num_predict")
    if _np_raw is None:
        _np_raw = os.getenv("NEO4J_SYNTHESIS_NUM_PREDICT")
    try:
        num_predict = int(_np_raw) if _np_raw is not None and str(_np_raw).strip() != "" else 2048
    except (TypeError, ValueError):
        num_predict = 2048
    num_predict = max(256, min(num_predict, 8192))

    backend = synthesis_backend()
    if backend == "openrouter":
        or_model = (
            os.getenv("OPENROUTER_MODEL")
            or str(cfg.get("openrouter_model") or "").strip()
            or None
        )
        max_tok = min(num_predict, 4096)
        return chat_openrouter(
            prompt,
            model=or_model,
            timeout=timeout,
            temperature=temp,
            max_tokens=max_tok,
        )

    return chat_ollama(
        prompt,
        host=host,
        model=model,
        timeout=timeout,
        temperature=temp,
        num_predict=num_predict,
    )
