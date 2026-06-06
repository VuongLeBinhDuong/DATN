"""Agent service - orchestrates agent execution.

Provides unified interface for ReAct agent with Intent Router.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import Any

from agent.react import ReActAgent
from core.llm_backends import LLMBackendError, get_llm_backend
from core.settings import Settings, get_settings

logger = logging.getLogger(__name__)


class AgentService:
    """Service for executing agent queries with ReAct strategy."""

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

    def execute(
        self,
        message: str,
        strategy: str = "auto",
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Execute agent query with ReAct strategy."""
        # 1. 0ms Intent Router Check
        from core.intent_router import detect_intent, execute_direct_db_query
        intent = detect_intent(message)
        if intent == "direct_db":
            return execute_direct_db_query(message)

        return self._run_react(message, history=history)

    def execute_stream(
        self,
        message: str,
        strategy: str = "auto",
        history: list[dict[str, str]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Execute agent query with streaming events."""
        # 1. 0ms Intent Router Check
        from core.intent_router import detect_intent, execute_direct_db_query
        intent = detect_intent(message)
        if intent == "direct_db":
            res = execute_direct_db_query(message)
            yield {
                "event": "step",
                "iteration": 1,
                "thought": "Quyết định từ Intent Router: Chuyển hướng xử lý 0ms..."
            }
            yield {
                "event": "reasoning_delta",
                "text": "Phát hiện câu hỏi tra cứu chỉ số sinh học lâm sàng chuẩn. Đang đối chiếu khoảng tham chiếu Việt Nam/WHO (0ms)...\n"
            }
            yield {
                "event": "answer_start"
            }
            yield {
                "event": "answer_delta",
                "text": res["answer"]
            }
            yield {
                "event": "done",
                "answer": res["answer"],
                "sources": res.get("sources", []),
                "context_graphrag_full": "",
                "drug_images": []
            }
            return

        agent = ReActAgent(
            llm_backend=self.llm,
            max_iterations=self.settings.agent.react_max_iter,
            parse_retries=self.settings.agent.react_parse_retries,
        )
        yield from agent.run_stream(message, history=history)

    def _run_react(self, message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Run ReAct agent."""
        agent = ReActAgent(
            llm_backend=self.llm,
            max_iterations=self.settings.agent.react_max_iter,
            parse_retries=self.settings.agent.react_parse_retries,
        )
        return agent.run_sync(message, history=history)

    def is_available(self) -> bool:
        """Check if agent service is ready."""
        try:
            return self.llm.is_available()
        except LLMBackendError:
            return False
