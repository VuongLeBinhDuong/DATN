"""Health check endpoints.

- GET /: Root redirect or API info
- GET /health: Basic health check
- GET /health/ready: Detailed readiness with dependencies
- GET /health/performance: Cache and connection pool stats
"""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse

from core.cache import get_query_cache
from core.connection_pool import get_driver_stats
from core.settings import SettingsDep
from core.settings import get_settings
from llm_pipeline.readiness import compute_readiness

router = APIRouter(tags=["health"])


@router.get("/", response_model=None)
async def root(settings: SettingsDep) -> Union[RedirectResponse, dict[str, str]]:
    """Root redirect to UI or API info."""
    if settings.web_ui_dir.is_dir():
        return RedirectResponse(url="/ui/")
    return {
        "service": "GraphRAG API",
        "docs": "/docs",
        "health": "/health",
        "health_ready": "/health/ready",
    }


@router.get("/health")
async def health() -> dict[str, str]:
    """Basic health check - returns OK if server is running."""
    return {"status": "ok"}


@router.get("/health/ready")
async def health_ready() -> dict:
    """Detailed readiness check.
    
    Checks all dependencies:
    - Ollama LLM availability
    - Neo4j connection (if enabled)
    - GraphRAG index status
    - Milvus configuration (if enabled)
    
    Returns comprehensive status for monitoring and debugging.
    """
    return compute_readiness()


@router.get("/health/config")
async def health_config() -> dict:
    """Expose current configuration (safe values only).
    
    Shows which LLM backend is active without exposing secrets.
    Mặc định ưu tiên Ollama, chỉ dùng OpenRouter khi explicitly set LLM_BACKEND.
    """
    import os
    
    backend = os.getenv("LLM_BACKEND", "ollama").lower()
    
    # Mặc định Ollama, chỉ đổi khi explicitly set
    if backend == "openrouter":
        active_backend = "openrouter"
    elif backend == "openai":
        active_backend = "openai"
    else:
        active_backend = "ollama"
    
    use_ollama = active_backend == "ollama"
    
    return {
        "llm_backend": {
            "active": active_backend,
            "configured": backend,
            "use_ollama": use_ollama,
            "ollama_host": os.getenv("OLLAMA_HOST", "http://localhost:11434") if use_ollama else None,
            "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.2:3b") if use_ollama else None,
            "openrouter_model": os.getenv("OPENROUTER_MODEL") if not use_ollama else None,
        },
        "neo4j": {
            "enabled": os.getenv("NEO4J_ENABLED", "true") == "true",
            "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        },
        "available_backends": ["ollama", "openrouter", "openai"],
    }


@router.get("/health/performance")
async def health_performance() -> dict:
    """Performance metrics for cache and connection pools.

    Returns cache hit rates and connection pool statistics
    for monitoring query performance.
    """
    cache = get_query_cache()
    pool_stats = get_driver_stats()

    return {
        "cache": cache.stats(),
        "connection_pool": pool_stats,
    }
