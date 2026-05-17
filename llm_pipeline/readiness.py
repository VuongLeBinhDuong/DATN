"""Kiểm tra sẵn sàng từng thành phần (không chặn API) — hỗ trợ demo và gỡ lỗi E2E."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _default_store_config_path() -> Path:
    return _repo_root() / "config" / "store.json"

# Lazy import settings to avoid circular deps
def _get_ollama_host() -> str:
    try:
        from core.settings import get_settings
        return get_settings().ollama.host
    except Exception:
        return (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")

try:
    from neo4j import GraphDatabase
except ImportError:
    GraphDatabase = None  # type: ignore[misc, assignment]

_READINESS_IO_SEC = float(os.getenv("READINESS_IO_TIMEOUT_SEC", "4"))


def _neo4j_config_path() -> Path:
    return _repo_root() / "config" / "neo4j.json"


def load_neo4j_config() -> dict[str, Any] | None:
    """Giống ``neo4j_graphrag.load_neo4j_config`` — tách riêng để ``readiness`` không import nặng."""
    p = _neo4j_config_path()
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def neo4j_enabled(cfg: dict[str, Any] | None) -> bool:
    if not cfg:
        return False
    return bool(cfg.get("enabled")) and cfg.get("query_backend") == "neo4j"


def _normalize_bolt_uri(uri: str) -> str:
    try:
        p = urlparse((uri or "").strip())
        if p.scheme and p.hostname and p.hostname.lower() == "localhost":
            port = p.port or 7687
            return urlunparse((p.scheme, f"127.0.0.1:{port}", p.path or "", "", "", ""))
    except Exception as e:
        logging.getLogger(__name__).debug("URL parse failed for %s: %s", uri, e)
    return uri


def _graphrag_parquet_ready() -> dict[str, Any]:
    root = _repo_root() / "graphrag"
    if not root.is_dir():
        return {"ok": False, "detail": "Thiếu thư mục graphrag/", "data_dir": None}
    for name in ("update_output", "output"):
        d = root / name
        if (d / "entities.parquet").is_file():
            return {"ok": True, "detail": "OK", "data_dir": str(d)}
    return {
        "ok": False,
        "detail": "Chưa có entities.parquet trong graphrag/output hoặc graphrag/update_output",
        "data_dir": None,
    }


def _ollama_ready() -> dict[str, Any]:
    # Mặc định ưu tiên Ollama, chỉ skip khi explicitly set LLM_BACKEND=openrouter/openai
    llm_backend = os.getenv("LLM_BACKEND", "ollama").lower()
    
    if llm_backend in ("openrouter", "openai"):
        return {
            "ok": True,
            "enabled": False,
            "detail": f"Đang dùng API key backend: {llm_backend} (không cần Ollama)",
            "host": None,
            "model_env": None,
            "model_available": None,
        }
    
    host = _get_ollama_host()
    model = (os.getenv("OLLAMA_MODEL") or "llama3.1:8b").strip()
    try:
        r = requests.get(f"{host}/api/tags", timeout=3)
        r.raise_for_status()
        data = r.json()
    except requests.RequestException as e:
        return {
            "ok": False,
            "detail": str(e),
            "host": host,
            "model_env": model,
            "model_available": False,
        }
    names: list[str] = []
    for m in data.get("models") or []:
        if isinstance(m, dict) and m.get("name"):
            names.append(str(m["name"]))
    model_ok = any(n == model or n.startswith(model + ":") for n in names)
    return {
        "ok": True,
        "detail": "OK" if model_ok else f"Chưa có model '{model}' trên Ollama (ollama pull …)",
        "host": host,
        "model_env": model,
        "model_available": model_ok,
    }


def _neo4j_ready(cfg: dict[str, Any] | None) -> dict[str, Any]:
    if cfg is None:
        cfg = load_neo4j_config()
    if not neo4j_enabled(cfg):
        return {
            "ok": True,
            "enabled": False,
            "detail": "Tắt trong config (không dùng Neo4j làm query backend)",
            "graph_populated": None,
        }
    if GraphDatabase is None:
        return {
            "ok": False,
            "enabled": True,
            "detail": "Chưa cài neo4j driver (pip install neo4j)",
            "graph_populated": False,
        }
    uri = os.getenv("NEO4J_URI") or cfg.get("uri")
    user = os.getenv("NEO4J_USER") or cfg.get("user")
    password = os.getenv("NEO4J_PASSWORD") or cfg.get("password")
    database = os.getenv("NEO4J_DATABASE") or cfg.get("database") or "neo4j"
    if not uri or not user or password is None:
        return {
            "ok": False,
            "enabled": True,
            "detail": "Thiếu uri / user / password trong config hoặc biến môi trường",
            "graph_populated": False,
        }
    uri_n = _normalize_bolt_uri(str(uri))
    driver = None
    try:
        driver = GraphDatabase.driver(
            uri_n,
            auth=(str(user), str(password)),
            connection_timeout=_READINESS_IO_SEC,
            connection_acquisition_timeout=_READINESS_IO_SEC,
        )
        driver.verify_connectivity()
        with driver.session(database=str(database)) as session:
            rec = session.run(
                "CALL db.labels() YIELD label AS l WHERE l = 'GraphEntity' RETURN l LIMIT 1"
            ).single()
        populated = rec is not None
        return {
            "ok": True,
            "enabled": True,
            "detail": "OK" if populated else "Kết nối OK nhưng chưa import GraphEntity (chạy sync Neo4j)",
            "graph_populated": populated,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "ok": False,
            "enabled": True,
            "detail": str(e),
            "graph_populated": False,
        }
    finally:
        if driver is not None:
            driver.close()

def compute_readiness() -> dict[str, Any]:
    """Trả về snapshot không ném exception (phù hợp gắn vào /health/ready)."""
    neo_cfg = load_neo4j_config()
    ollama = _ollama_ready()
    neo4j = _neo4j_ready(neo_cfg)
    graphrag_index = _graphrag_parquet_ready()

    knowledge_ok = False
    if neo4j.get("enabled"):
        knowledge_ok = bool(neo4j.get("ok") and neo4j.get("graph_populated"))
    else:
        knowledge_ok = bool(graphrag_index.get("ok"))

    # When using API key backend (ollama.enabled=false), don't require model_available
    ollama_ready = ollama.get("ok") and (
        ollama.get("model_available") or ollama.get("enabled") is False
    )
    agent_e2e_ready = bool(ollama_ready and knowledge_ok)

    return {
        "agent_e2e_ready": agent_e2e_ready,
        "ollama": ollama,
        "neo4j": neo4j,
        "graphrag_index": graphrag_index,
        }
