"""Neo4j repository implementation for GraphRAG.
"""

from __future__ import annotations

import logging
import os
import re
import hashlib
import json
from typing import Any

from core.cache import get_query_cache

try:
    from neo4j import GraphDatabase
    HAS_NEO4J = True
except ImportError:
    HAS_NEO4J = False
    GraphDatabase = None

from llm_pipeline.neo4j_graphrag import load_neo4j_config, neo4j_enabled
from repositories.base import KnowledgeRepository, QueryResult

logger = logging.getLogger(__name__)


def _normalize_bolt_uri(uri: str) -> str:
    """Replace localhost with 127.0.0.1 to avoid IPv6 issues."""
    from urllib.parse import urlparse, urlunparse
    try:
        p = urlparse(uri.strip())
        if p.scheme and p.hostname and p.hostname.lower() == "localhost":
            port = p.port or 7687
            return urlunparse((p.scheme, f"127.0.0.1:{port}", p.path or "", "", "", ""))
    except Exception:
        pass
    return uri


def _fulltext_safe_query(q: str) -> str:
    """Sanitize query for Neo4j fulltext search."""
    t = (q or "").strip()
    if not t:
        return "*"
    t = re.sub(r'[~^*+\-:"]', " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    cap = max(256, min(int(os.getenv("NEO4J_FULLTEXT_QUERY_MAX_CHARS", "1024")), 4096))
    return t[:cap] if t else "*"


def _query_to_string(value: Any) -> str:
    """Convert query input to a stable string representation."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        return str(value)


class Neo4jRepository(KnowledgeRepository):
    """Neo4j-backed knowledge repository for GraphRAG."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or load_neo4j_config()
        self._driver = None

    def _get_connection_params(self) -> dict[str, str] | None:
        """Extract connection parameters from config."""
        uri = os.getenv("NEO4J_URI") or self.config.get("uri")
        user = os.getenv("NEO4J_USER") or self.config.get("user")
        password = os.getenv("NEO4J_PASSWORD") or self.config.get("password")
        
        if not all([uri, user, password]):
            return None
            
        return {
            "uri": _normalize_bolt_uri(str(uri)),
            "user": str(user),
            "password": str(password),
            "database": os.getenv("NEO4J_DATABASE") or self.config.get("database", "neo4j"),
        }

    def _ensure_driver(self) -> Any:
        """Lazy initialization of Neo4j driver."""
        if self._driver is None:
            params = self._get_connection_params()
            if not params:
                raise RuntimeError("Neo4j connection parameters not configured")
                
            if not HAS_NEO4J:
                raise RuntimeError("neo4j driver not installed")
                
            self._driver = GraphDatabase.driver(
                params["uri"],
                auth=(params["user"], params["password"]),
            )
        return self._driver

    def is_ready(self) -> bool:
        """Check if Neo4j is configured and reachable."""
        if not neo4j_enabled(self.config):
            return False
        if not HAS_NEO4J:
            return False
            
        params = self._get_connection_params()
        if not params:
            return False
            
        try:
            with GraphDatabase.driver(
                params["uri"],
                auth=(params["user"], params["password"]),
            ) as driver:
                driver.verify_connectivity()
                return True
        except Exception:
            return False

    def health_check(self) -> dict[str, Any]:
        """Return detailed health status."""
        if not neo4j_enabled(self.config):
            return {"ok": True, "enabled": False, "detail": "Disabled in config"}
            
        if not HAS_NEO4J:
            return {"ok": False, "enabled": True, "detail": "Driver not installed"}
            
        params = self._get_connection_params()
        if not params:
            return {"ok": False, "enabled": True, "detail": "Missing connection params"}
            
        try:
            with GraphDatabase.driver(
                params["uri"],
                auth=(params["user"], params["password"]),
            ) as driver:
                driver.verify_connectivity()
                with driver.session(database=params["database"]) as session:
                    rec = session.run(
                        "CALL db.labels() YIELD label AS l WHERE l = 'GraphEntity' RETURN l LIMIT 1"
                    ).single()
                    populated = rec is not None
                    return {
                        "ok": True,
                        "enabled": True,
                        "detail": "OK" if populated else "Connected but no GraphEntity nodes",
                        "graph_populated": populated,
                    }
        except Exception as e:
            return {"ok": False, "enabled": True, "detail": str(e)}

    def query(
        self,
        question: str,
        retrieval_query: str | None = None,
        top_k: int = 12,
        use_cache: bool = True,
    ) -> QueryResult:
        """Execute fulltext query against Neo4j with caching.

        Args:
            question: The query question
            retrieval_query: Optional specific retrieval query
            top_k: Number of top results
            use_cache: Whether to use query result caching
        """
        from llm_pipeline.neo4j_graphrag import retrieve_graph_context_with_sources

        rq = retrieval_query or question
        rq_text = _query_to_string(rq)

        # Try cache first
        if use_cache:
            cache = get_query_cache()
            digest = hashlib.sha1(rq_text.encode("utf-8")).hexdigest()[:12]
            cache_key = f"neo4j:{digest}:{top_k}"
            cached = cache.get(cache_key)
            if cached is not None:
                logger.debug("Neo4j query cache hit for: %s...", rq_text[:50])
                return QueryResult(
                    text=cached["context"],
                    sources=cached["hits"],
                    metadata={"backend": "neo4j", "query": rq_text, "cached": True},
                )

        # Execute query
        start_time = logging.getLogger(__name__).isEnabledFor(logging.DEBUG)
        if start_time:
            import time
            t0 = time.time()

        context, hits = retrieve_graph_context_with_sources(rq_text, self.config)

        if start_time:
            elapsed = time.time() - t0
            logger.debug("Neo4j query executed in %.3fs for: %s...", elapsed, rq_text[:50])

        # Cache the result
        if use_cache:
            cache.set(cache_key, {"context": context, "hits": hits}, ttl_sec=180)

        return QueryResult(
            text=context,
            sources=hits,
            metadata={"backend": "neo4j", "query": rq_text, "cached": False},
        )

    def close(self) -> None:
        """Close Neo4j driver connection."""
        if self._driver is not None:
            self._driver.close()
            self._driver = None
