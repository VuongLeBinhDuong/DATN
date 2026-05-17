"""API route modules.

Organized by domain:
- health.py: Health checks and readiness
- ollama.py: Ollama LLM proxy endpoints
- graphrag.py: GraphRAG query endpoints
- agent.py: Agent/ReAct endpoints
"""

from __future__ import annotations

from api.routes.agent import router as agent_router
from api.routes.auth import router as auth_router
from api.routes.graphrag import router as graphrag_router
from api.routes.health import router as health_router
from api.routes.ollama import router as ollama_router

__all__ = [
    "agent_router",
    "auth_router",
    "graphrag_router",
    "health_router",
    "ollama_router",
]
