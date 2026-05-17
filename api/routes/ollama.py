"""Ollama LLM proxy endpoints.

- GET /api/ollama/health: Check Ollama server status
- POST /api/ollama/chat: Direct chat with Ollama
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.dependencies import SettingsDep, check_rate_limit
from core.llm_backends import LLMBackendError, OllamaBackend

router = APIRouter(prefix="/api/ollama", tags=["ollama"])


class OllamaChatIn(BaseModel):
    """Request body for Ollama chat."""
    message: str = Field(..., min_length=1, max_length=32000)
    model: str | None = Field(
        default=None,
        description="Model name (default: from OLLAMA_MODEL env)"
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (default: 0.7)"
    )


class OllamaChatOut(BaseModel):
    """Response from Ollama chat."""
    model: str
    message: str


@router.get("/health")
async def ollama_health(settings: SettingsDep) -> dict:
    """Check Ollama server health and model availability.
    
    Returns:
        - ollama_host: The configured host URL
        - ollama_model_env: The expected model from config
        - model_available: Whether the model exists on server
        - models: List of available models (if server reachable)
    """
    backend = OllamaBackend(
        host=settings.ollama.host,
        timeout=10,
    )
    
    try:
        available = backend.is_available()
        models = backend.list_models() if available else []
        
        model_ok = any(
            m == settings.ollama.model or m.startswith(settings.ollama.model + ":")
            for m in models
        )
        
        return {
            "ollama_host": settings.ollama.host,
            "ollama_model_env": settings.ollama.model,
            "model_available": model_ok,
            "models": models,
        }
    except LLMBackendError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/chat", response_model=OllamaChatOut)
async def ollama_chat(
    body: OllamaChatIn,
    request: Request,
    settings: SettingsDep,
) -> OllamaChatOut:
    """Send chat completion request to Ollama.
    
    Uses the configured Ollama host or falls back to localhost.
    Model can be overridden in request body.
    """
    check_rate_limit(request, settings)
    
    backend = OllamaBackend(
        host=settings.ollama.host,
        timeout=settings.ollama.timeout,
    )
    
    try:
        response = backend.chat(
            prompt=body.message,
            model=body.model or settings.ollama.model,
            temperature=body.temperature or 0.7,
        )
        return OllamaChatOut(
            model=body.model or settings.ollama.model,
            message=response,
        )
    except LLMBackendError as e:
        status = 502 if e.status_code else 503
        raise HTTPException(status_code=status, detail=str(e))
