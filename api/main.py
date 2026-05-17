"""Refactored FastAPI application with modular routes.

Clean replacement for llm_pipeline/app.py (530 lines → 120 lines).
Routes split into focused modules:
- api/routes/health.py: Health checks
- api/routes/ollama.py: Ollama proxy
- api/routes/graphrag.py: GraphRAG queries
- api/routes/agent.py: Agent execution
"""

from __future__ import annotations

import logging
import shutil
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.dependencies import check_rate_limit, get_client_ip  # Re-export for routes
from api.routes import agent_router, auth_router, graphrag_router, health_router, ollama_router
from api.routes.graphrag import QueryOut as QueryOut  # Re-export for compatibility
from core.settings import get_settings
from medical_records.api_router import router as medical_record_router
from medical_records.storage_paths import cleanup_roots_on_exit, pill_image_dataset_dir

logger = logging.getLogger(__name__)

# Re-export commonly used items for route modules
__all__ = ["app", "check_rate_limit", "get_client_ip"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    yield
    # Cleanup on shutdown
    for root in cleanup_roots_on_exit():
        if root.is_dir():
            try:
                shutil.rmtree(root, ignore_errors=False)
                logger.info("Cleaned up: %s", root)
            except OSError as e:
                logger.warning("Cleanup failed for %s: %s", root, e)


def create_app() -> FastAPI:
    """Application factory with dependency injection."""
    settings = get_settings()

    app = FastAPI(
        title="GraphRAG API",
        version="1.1.0",
        lifespan=lifespan,
    )

    # CORS middleware
    origins = settings.cors.get_origins_list()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    if settings.web_ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(settings.web_ui_dir), html=True), name="ui")

    # Pill images static files
    pill_root = pill_image_dataset_dir()
    if pill_root.is_dir():
        app.mount(
            "/api/pill-images/static",
            StaticFiles(directory=str(pill_root)),
            name="pill_images",
        )

    return app


# Create app instance
app = create_app()

# Include modular routers
app.include_router(health_router)
app.include_router(ollama_router)
app.include_router(graphrag_router)
app.include_router(agent_router)
app.include_router(auth_router)

# Include medical records router (legacy)
app.include_router(
    medical_record_router,
    prefix="/api/medical-record",
    tags=["medical-record"],
)
