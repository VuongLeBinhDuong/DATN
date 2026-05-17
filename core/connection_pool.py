"""Connection pooling for Neo4j to improve query performance.

Provides singleton driver instances with connection pooling configuration.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from core.settings import get_settings

logger = logging.getLogger(__name__)

# Thread-local storage for drivers
_thread_local = threading.local()

# Global driver cache
_drivers: dict[str, Any] = {}
_lock = threading.RLock()


def _make_driver_key(uri: str, user: str, database: str) -> str:
    """Create unique key for driver configuration."""
    return f"{uri}@{user}#{database}"


def _normalize_bolt_uri(uri: str) -> str:
    """Replace localhost with 127.0.0.1 to avoid IPv6 issues."""
    from urllib.parse import urlparse, urlunparse

    try:
        p = urlparse((uri or "").strip())
        if p.scheme and p.hostname and p.hostname.lower() == "localhost":
            port = p.port or 7687
            return urlunparse((p.scheme, f"127.0.0.1:{port}", p.path or "", "", "", ""))
    except Exception as e:
        logger.debug("URL parse failed for %s: %s", uri, e)
    return uri


def get_neo4j_driver(
    uri: str,
    user: str,
    password: str,
    *,
    max_connection_pool_size: int = 50,
    connection_timeout: int = 30,
    max_transaction_retry_time: int = 30,
) -> Any:
    """Get or create Neo4j driver with connection pooling.

    Reuses existing driver for same configuration to avoid connection overhead.

    Args:
        uri: Neo4j bolt URI
        user: Username
        password: Password
        max_connection_pool_size: Max connections in pool
        connection_timeout: Connection timeout in seconds
        max_transaction_retry_time: Max retry time for transactions

    Returns:
        Neo4j Driver instance
    """
    try:
        from neo4j import GraphDatabase
    except ImportError:
        return None

    uri = _normalize_bolt_uri(uri)
    key = _make_driver_key(uri, user, "")

    with _lock:
        if key not in _drivers:
            logger.info("Creating new Neo4j driver pool for %s", uri.replace("//", "//***@"))
            driver = GraphDatabase.driver(
                uri,
                auth=(user, password),
                max_connection_pool_size=max_connection_pool_size,
                connection_timeout=connection_timeout,
                max_transaction_retry_time=max_transaction_retry_time,
            )
            _drivers[key] = driver

        return _drivers[key]


def close_all_drivers() -> int:
    """Close all pooled drivers and clear cache.

    Returns:
        Number of drivers closed
    """
    global _drivers

    with _lock:
        count = 0
        for key, driver in list(_drivers.items()):
            try:
                driver.close()
                logger.info("Closed Neo4j driver: %s", key.replace("//", "//***@"))
                count += 1
            except Exception as e:
                logger.warning("Error closing driver %s: %s", key, e)
        _drivers.clear()
        return count


def get_driver_stats() -> dict[str, Any]:
    """Get connection pool statistics."""
    with _lock:
        stats = {
            "pooled_drivers": len(_drivers),
            "connections": [],
        }

        for key in _drivers:
            # Mask credentials in key
            safe_key = key.split("@")[0] + "@***"
            stats["connections"].append(safe_key)

        return stats


def configure_pool_from_settings() -> dict[str, Any]:
    """Configure pool settings from application settings."""
    settings = get_settings()

    pool_config = {
        "max_connection_pool_size": getattr(settings, "NEO4J_MAX_POOL_SIZE", 50),
        "connection_timeout": getattr(settings, "NEO4J_CONNECTION_TIMEOUT", 30),
        "max_transaction_retry_time": getattr(settings, "NEO4J_RETRY_TIME", 30),
    }

    return pool_config
