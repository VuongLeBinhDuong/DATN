"""FastAPI dependency injection providers.

Centralizes creation of shared resources:
- Settings
- LLM backends
- Knowledge repositories
- Services
- Rate limiting
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from core.llm_backends import LLMBackend, get_llm_backend
from core.settings import Settings, get_settings
from repositories.base import KnowledgeRepository
from repositories.factory import get_default_repository
from services.agent_service import AgentService

# In-memory rate limiter (replace with Redis for production)
_rate_limit_store: dict[str, list[float]] = {}


async def get_settings_dep() -> Settings:
    """Provide cached settings instance."""
    return get_settings()


async def get_llm_backend_dep(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> LLMBackend:
    """Provide LLM backend instance (auto-detects from env)."""
    return get_llm_backend(backend="auto")


async def get_knowledge_repo() -> KnowledgeRepository:
    """Provide knowledge repository instance."""
    return get_default_repository()


async def get_agent_service(
    settings: Annotated[Settings, Depends(get_settings_dep)],
    llm: Annotated[LLMBackend, Depends(get_llm_backend_dep)],
) -> AgentService:
    """Provide agent service with dependencies."""
    return AgentService(settings=settings, llm_backend=llm)


# Type aliases for cleaner route signatures
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
LLMBackendDep = Annotated[LLMBackend, Depends(get_llm_backend_dep)]
KnowledgeRepoDep = Annotated[KnowledgeRepository, Depends(get_knowledge_repo)]
AgentServiceDep = Annotated[AgentService, Depends(get_agent_service)]


def get_client_ip(request: Request) -> str:
    """Extract client IP for rate limiting."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request, settings: Settings) -> None:
    """Check if request exceeds rate limit.
    
    Args:
        request: FastAPI request object
        settings: Application settings with rate limit config
        
    Raises:
        HTTPException: 429 if rate limit exceeded
    """
    max_requests = settings.rate_limit.max_per_window
    if max_requests <= 0:
        return

    ip = get_client_ip(request)
    now = time.monotonic()
    window_start = now - settings.rate_limit.window_sec

    # Clean old entries and check limit
    hits = _rate_limit_store.setdefault(ip, [])
    hits[:] = [h for h in hits if h >= window_start]

    if len(hits) >= max_requests:
        raise HTTPException(status_code=429, detail="Too many requests; try again later.")

    hits.append(now)
