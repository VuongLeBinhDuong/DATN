"""Centralized settings management with Pydantic validation.

Replaces scattered os.getenv() calls throughout the codebase.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _repo_root() -> Path:
    """Get repository root path."""
    return Path(__file__).resolve().parents[1]


class OllamaSettings(BaseSettings):
    """Ollama LLM configuration."""

    model_config = SettingsConfigDict(
        env_prefix="OLLAMA_",
        extra="ignore",
    )

    host: str = Field(default="http://localhost:11434", description="Ollama server URL")
    model: str = Field(default="llama3.1:8b", description="Default model name")
    timeout: int = Field(default=120, ge=1, le=600, description="Request timeout in seconds")
    router_model: str = Field(default="llama3.1:8b", description="Model for routing decisions")

    @field_validator("host")
    @classmethod
    def validate_host(cls, v: str) -> str:
        """Ensure host URL is valid format."""
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"OLLAMA_HOST must start with http:// or https://: {v}")
        return v.rstrip("/")


class OpenRouterSettings(BaseSettings):
    """OpenRouter API configuration."""

    model_config = SettingsConfigDict(
        env_prefix="OPENROUTER_",
        extra="ignore",
    )

    api_key: str | None = Field(default=None, description="OpenRouter API key")
    model: str | None = Field(default=None, description="Model identifier")
    api_base: str = Field(default="https://openrouter.ai/api/v1", description="API base URL")


class Neo4jSettings(BaseSettings):
    """Neo4j graph database configuration."""

    model_config = SettingsConfigDict(
        env_prefix="NEO4J_",
        extra="ignore",
    )

    uri: str | None = Field(default=None, description="Bolt connection URI")
    user: str | None = Field(default=None, description="Database user")
    password: str | None = Field(default=None, description="Database password")
    database: str = Field(default="neo4j", description="Database name")
    enabled: bool = Field(default=False, description="Use Neo4j as query backend")

    @field_validator("uri")
    @classmethod
    def validate_uri(cls, v: str | None) -> str | None:
        """Ensure URI uses bolt protocol."""
        if v and not v.startswith("bolt://"):
            raise ValueError(f"NEO4J_URI must start with bolt://: {v}")
        return v


class RateLimitSettings(BaseSettings):
    """Rate limiting configuration."""

    model_config = SettingsConfigDict(
        env_prefix="RATE_",
        extra="ignore",
    )

    window_sec: int = Field(default=60, ge=1, description="Time window in seconds")
    max_per_window: int = Field(default=30, ge=0, description="Max requests per window (0=unlimited)")


class AgentSettings(BaseSettings):
    """Agent/ReAct configuration."""

    model_config = SettingsConfigDict(
        env_prefix="AGENT_",
        extra="ignore",
    )

    use_legacy_pipeline: bool = Field(default=False, description="Use legacy orchestrator")
    use_langgraph: bool = Field(default=False, description="Use LangGraph workflow")
    use_react: bool = Field(default=True, description="Use ReAct pattern (default)")
    react_max_iter: int = Field(default=3, ge=1, le=10, description="Max ReAct iterations")
    react_parse_retries: int = Field(default=2, ge=0, le=5, description="Parse retry attempts")
    react_num_predict: int = Field(default=1024, ge=256, le=8192, description="Max tokens per response")
    trace: bool = Field(default=True, description="Enable agent tracing logs")


class VectorStoreSettings(BaseSettings):
    """Milvus/Zilliz vector store configuration."""

    model_config = SettingsConfigDict(
        env_prefix="STORE_",
        extra="ignore",
    )

    uri: str = Field(default="http://localhost:19530", description="Milvus server URI")
    collection: str = Field(default="chunks", description="Default collection name")
    config_path: Path = Field(default=Path("config/store.json"), description="Config file path")
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="Embedding model name",
    )

    # Legacy env var support
    @field_validator("uri", mode="before")
    @classmethod
    def legacy_milvus_uri(cls, v: str | None) -> str:
        """Support legacy MILVUS_URI env var."""
        if v is None:
            return os.getenv("MILVUS_URI", "http://localhost:19530")
        return v


class CorsSettings(BaseSettings):
    """CORS middleware configuration."""

    origins: str = Field(default="*", description="Allowed origins (comma-separated)")

    def get_origins_list(self) -> list[str]:
        """Parse origins string to list."""
        raw = self.origins.strip()
        if raw == "*":
            return ["*"]
        return [x.strip() for x in raw.split(",") if x.strip()]


class Settings(BaseSettings):
    """Global application settings.
    
    Loads from:
    1. Environment variables
    2. .env file in repo root
    3. config/.env file (overrides)
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Nested settings
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    openrouter: OpenRouterSettings = Field(default_factory=OpenRouterSettings)
    neo4j: Neo4jSettings = Field(default_factory=Neo4jSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    cors: CorsSettings = Field(default_factory=CorsSettings)

    # General
    debug: bool = Field(default=False, description="Debug mode")
    expose_retrieval_debug: bool = Field(
        default=False,
        description="Expose retrieval confidence in API responses",
    )

    # Paths
    @property
    def repo_root(self) -> Path:
        """Repository root directory."""
        return _repo_root()

    @property
    def web_ui_dir(self) -> Path:
        """Web UI static files directory."""
        return self.repo_root / "web_ui"

    @property
    def prompts_dir(self) -> Path:
        """Prompt templates directory."""
        raw = os.getenv("LLM_APP_PROMPTS_DIR")
        if raw:
            return Path(raw).expanduser().resolve()
        return self.repo_root / "prompts"

    @property
    def neo4j_config_path(self) -> Path:
        """Neo4j JSON config path."""
        return self.repo_root / "config" / "neo4j.json"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance.
    
    Uses LRU cache to avoid re-parsing on every call.
    """
    # Load dotenv files first
    _load_dotenv_files()
    return Settings()


def _is_running_in_docker() -> bool:
    """Detect if running inside a Docker container.
    
    Checks for:
    - /.dockerenv file exists
    - /proc/self/cgroup contains "docker"
    """
    if os.getenv("RUNNING_IN_DOCKER") == "1":
        return True
    # Check for .dockerenv file
    if Path("/.dockerenv").exists():
        return True
    
    # Check cgroup
    try:
        cgroup_path = Path("/proc/self/cgroup")
        if cgroup_path.is_file():
            content = cgroup_path.read_text(encoding="utf-8")
            if "docker" in content:
                return True
    except Exception:
        pass
    
    return False


def _load_dotenv_files() -> None:
    """Load environment files in correct order.
    
    Skip loading .env files when running inside Docker container
    to respect env vars from docker-compose.yml or Dockerfile.
    """
    # Skip loading .env files when running in Docker container
    # to allow docker-compose.yml environment variables to take effect
    if _is_running_in_docker():
        return
    
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    root = _repo_root()
    p_root = root / ".env"
    p_cfg = root / "config" / ".env"

    if p_root.is_file():
        load_dotenv(p_root)
    if p_cfg.is_file():
        load_dotenv(p_cfg, override=True)


# FastAPI dependency type alias
from typing import Annotated
from fastapi import Depends

SettingsDep = Annotated[Settings, Depends(get_settings)]
