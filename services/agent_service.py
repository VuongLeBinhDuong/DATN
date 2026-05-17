"""Agent service - orchestrates different agent execution strategies.

Provides unified interface for:
- ReAct agent (default)
- Legacy orchestrator
- LangGraph workflow
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from agent.orchestrator import run_agent_demo
from agent.react import ReActAgent
from agent.router import DEFAULT_ROUTER_MODEL
from core.llm_backends import LLMBackendError, get_llm_backend
from core.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class AgentService:
    """Service for executing agent queries with different strategies."""

    def __init__(
        self,
        settings: Settings | None = None,
        llm_backend: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.llm = llm_backend or self._create_llm_backend()

    def _create_llm_backend(self) -> Any:
        """Create default LLM backend from settings."""
        return get_llm_backend(backend="auto")

    def _should_use_legacy(self, force_legacy: bool = False) -> bool:
        """Determine if legacy pipeline should be used."""
        if force_legacy:
            return True
        return self.settings.agent.use_legacy_pipeline or not self.settings.agent.use_react

    def _should_use_langgraph(self, force_langgraph: bool = False) -> bool:
        """Determine if LangGraph should be used."""
        if not force_langgraph:
            return False
        try:
            from agent.langgraph_app import run_agent_demo_langgraph
            return run_agent_demo_langgraph is not None
        except ImportError:
            logger.warning("LangGraph requested but not installed")
            return False

    def execute(
        self,
        message: str,
        strategy: str = "auto",
        use_legacy: bool = False,
        use_langgraph: bool = False,
    ) -> dict[str, Any]:
        """Execute agent query with appropriate strategy."""
        if self._should_use_langgraph(use_langgraph):
            return self._run_langgraph(message, strategy)

        if self._should_use_legacy(use_legacy):
            return self._run_legacy(message, strategy)

        return self._run_react(message)

    def execute_stream(
        self,
        message: str,
        strategy: str = "auto",
    ) -> Iterator[dict[str, Any]]:
        """Execute agent query with streaming events."""
        if self._should_use_legacy():
            raise ValueError("Streaming not supported for legacy pipeline")

        if self._should_use_langgraph():
            raise ValueError("Streaming not supported for LangGraph")

        agent = ReActAgent(
            llm_backend=self.llm,
            max_iterations=self.settings.agent.react_max_iter,
            parse_retries=self.settings.agent.react_parse_retries,
        )
        yield from agent.run_stream(message)

    def _run_react(self, message: str) -> dict[str, Any]:
        """Run ReAct agent."""
        agent = ReActAgent(
            llm_backend=self.llm,
            max_iterations=self.settings.agent.react_max_iter,
            parse_retries=self.settings.agent.react_parse_retries,
        )
        return agent.run_sync(message)

    def _run_legacy(self, message: str, strategy: str) -> dict[str, Any]:
        """Run legacy orchestrator."""
        return run_agent_demo(
            message,
            strategy=strategy,
            config_path=None,
            ollama_model=self.settings.ollama.model,
            router_model=self.settings.ollama.router_model or DEFAULT_ROUTER_MODEL,
            ollama_host=self.settings.ollama.host,
            ollama_timeout=self.settings.ollama.timeout,
        )

    def _run_langgraph(self, message: str, strategy: str) -> dict[str, Any]:
        """Run LangGraph workflow."""
        try:
            from agent.langgraph_app import run_agent_demo_langgraph
        except ImportError as e:
            raise LLMBackendError("LangGraph not installed") from e

        return run_agent_demo_langgraph(
            message,
            strategy=strategy,
            config_path=None,
            ollama_model=self.settings.ollama.model,
            router_model=self.settings.ollama.router_model or DEFAULT_ROUTER_MODEL,
            ollama_host=self.settings.ollama.host,
            ollama_timeout=self.settings.ollama.timeout,
        )

    def is_available(self) -> bool:
        """Check if agent service is ready."""
        try:
            return self.llm.is_available()
        except LLMBackendError:
            return False
