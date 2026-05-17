"""Core module: base classes, settings, and shared utilities."""

from __future__ import annotations

from core.cache import get_query_cache, SimpleCache
from core.connection_pool import get_neo4j_driver, close_all_drivers, get_driver_stats
from core.settings import Settings, get_settings
from core.llm_backends import LLMBackend, OllamaBackend, OpenRouterBackend

__all__ = [
    "get_query_cache",
    "SimpleCache",
    "get_neo4j_driver",
    "close_all_drivers",
    "get_driver_stats",
    "Settings",
    "get_settings",
    "LLMBackend",
    "OllamaBackend",
    "OpenRouterBackend",
]
