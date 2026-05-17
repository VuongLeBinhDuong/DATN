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
    """Giống ``retrieve_graph_context`` nhưng trả thêm danh sách nguồn (title/score) cho UI."""
    if GraphDatabase is None:
        return "Neo4j: chưa cài driver. Chạy: pip install neo4j", []

    uri = os.getenv("NEO4J_URI") or cfg.get("uri")
    user = os.getenv("NEO4J_USER") or cfg.get("user")
    password = os.getenv("NEO4J_PASSWORD") or cfg.get("password")
    database = os.getenv("NEO4J_DATABASE") or cfg.get("database") or "neo4j"
    idx = _safe_index_name(str(cfg.get("fulltext_index_name") or "graphEntityFulltext"))
    idx_comm = _safe_index_name(str(cfg.get("community_fulltext_index_name") or "communityFulltext"))
    top_k = max(1, min(int(cfg.get("top_k_nodes") or 12), 48))
    hops = max(0, min(int(cfg.get("neighbor_hops") or 1), 2))
    top_comm = max(1, min(int(cfg.get("top_communities") or 8), 24))
    include_comm = bool(cfg.get("include_community_reports", True))
    comm_fulltext = bool(cfg.get("community_fulltext_boost", True))

    if not uri or not user or password is None:
        return "Neo4j: thiếu uri/user/password trong config/neo4j.json hoặc biến môi trường.", []

    # Use connection pooling instead of creating new driver each time
    driver = get_neo4j_driver(uri, user, password)
    if driver is None:
        return "Neo4j: không thể tạo driver (chưa cài neo4j driver?).", []

    ft_query = _fulltext_safe_query(question)
    source_hits: list[dict[str, Any]] = []

    lines: list[str] = []
    try:
        with driver.session(database=database) as session:
            rows: list[dict[str, Any]] = []

            def _fulltext_entity_rows(q: str) -> list[dict[str, Any]]:
                try:
                    cypher = (
                        f"CALL db.index.fulltext.queryNodes('{idx}', $q) "
                        "YIELD node, score RETURN node AS n, score AS s LIMIT $lim"
                    )
                    return [dict(r) for r in session.run(cypher, {"q": q, "lim": top_k})]
                except Exception:
                    return []

            try:
                rows = _fulltext_entity_rows(ft_query)
                if not rows and ft_query not in ("", "*"):
                    parts = ft_query.split()
                    if len(parts) > 5:
                        rows = _fulltext_entity_rows(" ".join(parts[:5]))
                    if not rows and parts:
                        rows = _fulltext_entity_rows(parts[0])
            except Exception as exc:  # noqa: BLE001
                lines.append(f"[Neo4j fulltext entity: {exc} — fallback CONTAINS]\n")
                token = (question or "").strip().split()
                needle = (token[0] if token else "")[:80].lower()
                if needle and _graph_entity_label_in_use(session):
                    rows = [
                        dict(r)
                        for r in session.run(
                            "MATCH (n:GraphEntity) "
                            "WHERE toLower(coalesce(n.title,'')) CONTAINS $needle "
                            "   OR toLower(coalesce(n.description,'')) CONTAINS $needle "
                            "RETURN n AS n, 1.0 AS s LIMIT $lim",
                            {"needle": needle, "lim": top_k},
                        )
                    ]

            def node_id(node: Any) -> str:
                props = dict(node)
                return str(props.get("id") or "")

            seen: set[str] = set()
            ordered: list[dict[str, Any]] = []
            seed_ids: list[str] = []
            for r in rows:
                n = r["n"]
                i = node_id(n)
                if i and i not in seen:
                    seen.add(i)
                    seed_ids.append(i)
                    ordered.append({"node": n, "score": float(r.get("s") or 0.0)})

            lim2 = max(4, min(top_k // 2, 16))
            if hops >= 1 and seed_ids:
                try:
                    nbr = session.run(
                        "MATCH (n:GraphEntity)-[:RELATED]-(m:GraphEntity) "
                        "WHERE n.id IN $seed AND NOT m.id IN $seed "
                        "RETURN DISTINCT m AS n, 0.4 AS s LIMIT $lim2",
                        {"seed": seed_ids, "lim2": lim2},
                    )
                    for rec in nbr:
                        n = rec["n"]
                        i = node_id(n)
                        if i and i not in seen:
                            seen.add(i)
                            ordered.append({"node": n, "score": float(rec.get("s") or 0.4)})
                except Exception:
                    pass

            if hops >= 2 and seen:
                try:
                    boundary = list(seen)
                    nbr2 = session.run(
                        "MATCH (n:GraphEntity)-[:RELATED]-(m:GraphEntity) "
                        "WHERE n.id IN $ids AND NOT m.id IN $ids "
                        "RETURN DISTINCT m AS n, 0.25 AS s LIMIT $lim3",
                        {"ids": boundary, "lim3": lim2},
                    )
                    for rec in nbr2:
                        n = rec["n"]
                        i = node_id(n)
                        if i and i not in seen:
                            seen.add(i)
                            ordered.append({"node": n, "score": float(rec.get("s") or 0.25)})
                except Exception:
                    pass

            comm_summaries: list[tuple[float, str]] = []
            if include_comm and seed_ids:
                try:
                    cr = session.run(
                        "MATCH (e:GraphEntity)-[:IN_COMMUNITY]->(c:Community) "
                        "WHERE e.id IN $seed "
                        "RETURN DISTINCT c.community_id AS cid, c.level AS lvl, c.title AS ct, "
                        "c.summary AS cs, c.rank AS rk ORDER BY coalesce(rk,0) DESC LIMIT $tclim",
                        {"seed": seed_ids, "tclim": top_comm},
                    )
                    for rec in cr:
                        cs = (rec.get("cs") or "").strip()
                        if not cs:
                            continue
                        title = (rec.get("ct") or "").strip()
                        lvl = rec.get("lvl")
                        rk = float(rec.get("rk") or 0.0)
                        block = f"[L{lvl}] {title}\n{cs[:2500]}{'…' if len(cs) > 2500 else ''}"
                        comm_summaries.append((rk, block))
                except Exception:
                    pass

            if include_comm and comm_fulltext and len(comm_summaries) < top_comm:
                try:
                    cq = (
                        f"CALL db.index.fulltext.queryNodes('{idx_comm}', $q) "
                        "YIELD node, score RETURN node AS c, score AS s LIMIT $tclim"
                    )
                    for rec in session.run(cq, {"q": ft_query, "tclim": top_comm}):
                        cnode = rec["c"]
                        props = dict(cnode)
                        cs = (props.get("summary") or "").strip()
                        if not cs:
                            continue
                        title = (props.get("title") or "").strip()
                        lvl = props.get("level")
                        blk = f"[L{lvl}] {title}\n{cs[:2500]}{'…' if len(cs) > 2500 else ''}"
                        comm_summaries.append((float(rec.get("s") or 0.0), blk))
                except Exception:
                    pass

            if comm_summaries:
                comm_summaries.sort(key=lambda x: x[0], reverse=True)
                seen_txt: set[str] = set()
                lines.append("=== Community reports (GraphRAG hierarchical / QFS) ===")
                for sc_comm, blk in comm_summaries[:top_comm]:
                    if blk not in seen_txt:
                        seen_txt.add(blk)
                        ct = (blk.split("\n") or [""])[0].strip()[:240]
                        source_hits.append(
                            {
                                "title": ct or "Community report",
                                "link": "",
                                "source": "neo4j:Community",
                                "score": float(sc_comm),
                            }
                        )
                        lines.append(blk)
                        lines.append("")

            if not ordered and not comm_summaries:
                return "", []

            cap_nodes = max(top_k * 2, 16)
            for i, item in enumerate(ordered[:cap_nodes]):
                props = dict(item["node"])
                title = (props.get("title") or "").strip()
                typ = (props.get("type") or "").strip()
                desc = (props.get("description") or "").strip()
                pid = props.get("id", "")
                sc = float(item.get("score") or 0.0)
                source_hits.append(
                    {
                        "title": title or f"(GraphEntity {pid})",
                        "link": "",
                        "source": "neo4j:GraphEntity",
                        "score": sc,
                    }
                )
                lines.append(f"--- Entity [{i + 1}] (score≈{item['score']:.3f}) id={pid} ---")
                if title:
                    lines.append(f"title: {title}")
                if typ:
                    lines.append(f"type: {typ}")
                if desc:
                    cut = 2000
                    lines.append(f"description: {desc[:cut]}{'…' if len(desc) > cut else ''}")

            if seen:
                rel_result = session.run(
                    "MATCH (a:GraphEntity)-[r:RELATED]-(b:GraphEntity) "
                    "WHERE a.id IN $ids AND b.id IN $ids "
                    "RETURN coalesce(a.title,'') AS at, coalesce(b.title,'') AS bt, coalesce(r.weight,1.0) AS w LIMIT 40",
                    {"ids": list(seen)},
                )
                rel_lines: list[str] = []
                for rec in rel_result:
                    at = (rec.get("at") or "").strip()
                    bt = (rec.get("bt") or "").strip()
                    if at and bt:
                        rel_lines.append(f"  • {at} —[{rec.get('w')}]→ {bt}")
                if rel_lines:
                    lines.append("\n--- Quan hệ (trong tập trên) ---")
                    lines.extend(rel_lines[:40])
    finally:
        # Note: Don't close driver here - it's managed by connection pool
        pass

    return "\n".join(lines).strip(), source_hits


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
    model = os.getenv("OLLAMA_MODEL") or cfg.get("ollama_model") or "llama3.1:8b"
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
