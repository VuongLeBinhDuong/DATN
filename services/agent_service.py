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
        # 1. Social Shortcut: greetings, open-ended chit-chat, simple thanks
        from agent.router import is_obvious_pure_social, is_meta_conversational_opener
        if is_obvious_pure_social(message) or is_meta_conversational_opener(message):
            return self._run_direct_social(message)

        return self._run_react(message, history=history)

    def execute_stream(
        self,
        message: str,
        strategy: str = "auto",
        history: list[dict[str, str]] | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Execute agent query with streaming events."""
        # 1. Social Shortcut: greetings, open-ended chit-chat, simple thanks (Streaming)
        from agent.router import is_obvious_pure_social, is_meta_conversational_opener
        if is_obvious_pure_social(message) or is_meta_conversational_opener(message):
            yield {
                "event": "step",
                "iteration": 1,
                "thought": "Quyết định từ Intent Router: Phản hồi xã giao nhanh..."
            }
            yield {
                "event": "answer_start"
            }
            
            prompt_path = self.settings.prompts_dir / "social_turn_prompt.txt"
            if prompt_path.is_file():
                template = prompt_path.read_text(encoding="utf-8")
                prompt = template.format(question=message)
            else:
                prompt = f"Bạn là trợ lý y tế. Đáp lại lời xã giao sau thật ngắn gọn bằng tiếng Việt: {message}"
                
            ans_parts = []
            for chunk in self.llm.chat_stream(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            ):
                ans_parts.append(chunk)
                yield {"event": "answer_delta", "text": chunk}
                
            ans_text = "".join(ans_parts)
            yield {
                "event": "done",
                "answer": ans_text,
                "sources": [],
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

    def _run_direct_social(self, message: str) -> dict[str, Any]:
        """Generate conversational response bypassing ReAct agent loop."""
        prompt_path = self.settings.prompts_dir / "social_turn_prompt.txt"
        if prompt_path.is_file():
            template = prompt_path.read_text(encoding="utf-8")
            prompt = template.format(question=message)
        else:
            prompt = f"Bạn là trợ lý y tế. Đáp lại lời xã giao sau thật ngắn gọn bằng tiếng Việt: {message}"
            
        answer = self.llm.chat(prompt=prompt, temperature=0.5)
        
        return {
            "answer": answer,
            "strategy": "direct_llm",
            "plan": {"type": "direct_llm", "steps": [{"iteration": 1, "type": "social_shortcut"}]},
            "errors": [],
            "context_graphrag_preview": "",
            "context_graphrag_full": "",
            "context_graphrag_total_chars": 0,
            "drug_images": [],
            "sources": []
        }

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
