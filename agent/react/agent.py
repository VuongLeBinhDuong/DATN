"""Main ReAct Agent implementation.

Provides both synchronous and streaming execution modes.
Refactored from the original 752-line react_agent.py.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from typing import Any

import requests

from agent.react.parser import ReActParseResult, ReActParser
from agent.react.prompts import (
    create_recovery_synthetic_message,
    get_parse_retry_prompt,
    get_react_system_prompt,
)
from agent.react.tools import (
    merge_pill_observation,
    run_graphrag_tool,
    run_pill_image_tool,
)
from agent.retrieval_confidence import compute_retrieval_confidence
from agent.tools import merge_retrieval_hits
from core.llm_backends import LLMBackendError, OllamaBackend
from core.settings import get_settings

logger = logging.getLogger(__name__)


def _want_agent_terminal_log() -> bool:
    """Check if agent tracing is enabled."""
    settings = get_settings()
    return settings.agent.trace


def _recovery_enabled() -> bool:
    """Check if ReAct recovery mode is enabled."""
    settings = get_settings()
    return not settings.agent.use_legacy_pipeline


def _chunk_stream_answer(answer: str) -> Iterator[str]:
    """Yield answer in chunks for streaming response."""
    chunk_size = 4  # Could be configurable
    s = answer or ""
    for i in range(0, len(s), chunk_size):
        yield s[i : i + chunk_size]


def _append_answer_source_note(
    answer: str,
    graph_context: str,
    retrieval_hits: list[dict[str, Any]],
) -> str:
    """Append source/method note under answer for UI transparency."""
    base = (answer or "").strip()
    marker = "Nguồn trả lời:"
    if marker in base:
        return base

    if (graph_context or "").strip() or retrieval_hits:
        source_note = "RAG (GraphRAG + LLM tổng hợp)"
    else:
        source_note = "LLM trực tiếp (không dùng RAG)"

    if not base:
        return f"{marker} {source_note}"
    return f"{base}\n\n---\n{marker} {source_note}"


def _forced_finalize_answer(question: str, graph_context: str) -> str:
    """Fallback answer when model keeps looping on same tool calls."""
    context = (graph_context or "").strip()
    if not context:
        return "Mình chưa đủ dữ liệu để trả lời chắc chắn. Bạn có thể hỏi lại ngắn gọn hơn hoặc thêm triệu chứng cụ thể."
    preview = context[:1800]
    if len(context) > 1800:
        preview += "\n\n...(đã rút gọn ngữ cảnh tra cứu)"
    return (
        f"Dựa trên ngữ cảnh đã tra cứu cho câu hỏi '{question}', đây là các ý chính:\n\n"
        f"{preview}\n\n"
        "Nếu bạn muốn, mình có thể tóm tắt ngắn hơn theo dạng gạch đầu dòng dễ đọc."
    )


def _build_result_bundle(
    question: str,
    answer: str,
    graph_context: str,
    steps: list[dict[str, Any]],
    errors: list[str],
    drug_image_urls: list[str],
    retrieval_hits: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build standardized result bundle for API response."""
    raw_graph_context = getattr(graph_context, "raw_context", graph_context)
    answer = _append_answer_source_note(answer, graph_context, retrieval_hits)
    confidence = compute_retrieval_confidence(retrieval_hits, graph_context)

    return {
        "answer": answer,
        "strategy": "react",
        "plan": {"type": "react", "steps": steps},
        "errors": errors,
        "context_graphrag_preview": (raw_graph_context[:800] + "…") if len(raw_graph_context) > 800 else raw_graph_context,
        "context_graphrag_full": raw_graph_context,
        "context_graphrag_total_chars": len(raw_graph_context),
        "context_medication_preview": "",
        "drug_images": drug_image_urls,
        "medication_plan": [],
        "reminders": [],
        "sources": [
            {
                "title": hit.get("title", ""),
                "link": hit.get("link", ""),
                "source": hit.get("source", ""),
                "score": hit.get("score"),
            }
            for hit in retrieval_hits
        ],
        "retrieval_confidence": confidence,
    }


class ReActAgent:
    """ReAct agent with tool execution capabilities.
    
    Supports both synchronous and streaming execution modes.
    """

    def __init__(
        self,
        llm_backend: Any | None = None,
        max_iterations: int | None = None,
        parse_retries: int | None = None,
    ) -> None:
        settings = get_settings()

        self.llm = llm_backend or OllamaBackend(
            host=settings.ollama.host,
            timeout=settings.ollama.timeout,
        )
        self.max_iterations = max_iterations or settings.agent.react_max_iter
        self.parse_retries = parse_retries or settings.agent.react_parse_retries
        self.parser = ReActParser()
        self.system_prompt = get_react_system_prompt()

    def _create_initial_messages(self, question: str, history: list[dict[str, str]] | None = None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """Create initial message history with system prompt."""
        import re
        clean_history = []
        if history:
            for turn in history[-6:]:
                role = turn.get("role")
                content = turn.get("content")
                if role in ("user", "assistant") and content:
                    # Strip any HTML tags from web UI
                    clean_content = re.sub(r"<[^>]*>", "", content).strip()
                    if clean_content:
                        clean_history.append({"role": role, "content": clean_content})

        initial_msgs = [{"role": "system", "content": self.system_prompt}]
        for turn in clean_history:
            initial_msgs.append(turn)
        initial_msgs.append({"role": "user", "content": f"Question: {question}"})
        return initial_msgs, clean_history

    def _execute_tool(
        self,
        tool_name: str,
        tool_input: str | None,
        original_question: str,
        current_graph_context: str,
        current_image_urls: list[str],
    ) -> tuple[str, list[str], list[dict[str, Any]]]:
        """Execute a tool and return updated state.
        
        Returns:
            Tuple of (observation, updated_image_urls, retrieval_hits)
        """
        if tool_name == "medical_calculator":
            from agent.react.tools import run_medical_calculator_tool
            obs = run_medical_calculator_tool(tool_input)
            return obs, current_image_urls, []

        if tool_name == "drug_interaction_checker":
            from agent.react.tools import run_drug_interaction_checker_tool
            obs = run_drug_interaction_checker_tool(tool_input)
            return obs, current_image_urls, []

        if tool_name == "pill_image_lookup":
            obs, urls = run_pill_image_tool(tool_input)
            return obs, urls, []

        # graphrag_query (tắt Query Expansion trong ReAct để tối ưu hóa tốc độ)
        obs, hits = run_graphrag_tool(tool_input, original_question, use_expansion=False)
        raw_context = getattr(obs, "raw_context", obs)

        # Merge with auto-detected pill images
        merged_obs, updated_urls = merge_pill_observation(
            original_question, obs, current_image_urls
        )

        if raw_context:
            from agent.react.tools import ToolObservationStr
            merged_obs = ToolObservationStr(merged_obs, raw_context)

        return merged_obs, updated_urls, hits

    def run_sync(self, question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
        """Execute ReAct agent synchronously.
        
        Args:
            question: User question to answer
            history: Previous conversation turns
            
        Returns:
            Result bundle with answer and metadata
        """
        q = (question or "").strip()
        messages, clean_history = self._create_initial_messages(q, history)
        history_len = len(clean_history)

        errors: list[str] = []
        steps: list[dict[str, Any]] = []
        graph_context = ""
        drug_image_urls: list[str] = []
        retrieval_hits: list[dict[str, Any]] = []
        last_action_signature: tuple[str, str] | None = None

        for iteration in range(1, self.max_iterations + 1):
            assistant_text = ""
            last_parse_err = ""

            # Try parsing with retries
            for attempt in range(self.parse_retries):
                try:
                    assistant_text = "".join(self.llm.chat_stream(
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            *clean_history,
                            {"role": "user", "content": f"Question: {q}"},
                            *messages[2 + history_len:],  # ReAct iterations
                        ],
                        temperature=0.15,
                        stop=["Observation:"],
                    ))
                except LLMBackendError as exc:
                    errors.append(f"LLM: {exc}")
                    return _build_result_bundle(
                        q,
                        "Không thể kết nối mô hình. Vui lòng thử lại sau.",
                        graph_context,
                        steps,
                        errors,
                        drug_image_urls,
                        retrieval_hits,
                    )

                result = self.parser.parse(assistant_text)
                if result.kind != "error":
                    break

                last_parse_err = result.error_message or "parse"
                if _want_agent_terminal_log():
                    logger.warning(
                        "ReAct parse error iter=%s attempt=%s: %s | raw=%r",
                        iteration,
                        attempt + 1,
                        last_parse_err,
                        assistant_text[:500] + "…" if len(assistant_text) > 500 else assistant_text,
                    )

                # Add retry prompt
                messages.append({"role": "assistant", "content": assistant_text})
                messages.append({"role": "user", "content": get_parse_retry_prompt(last_parse_err)})
            else:
                # All retries exhausted - attempt recovery
                last_err = last_parse_err or "parse"

                if _recovery_enabled() and iteration == 1 and not graph_context.strip():
                    # Force graphrag_query with original question
                    obs, hits = run_graphrag_tool(q, q)
                    raw_context = getattr(obs, "raw_context", obs)
                    retrieval_hits = merge_retrieval_hits(retrieval_hits, hits)
                    obs, drug_image_urls = merge_pill_observation(q, obs, drug_image_urls)

                    if obs.strip():
                        from agent.react.tools import ToolObservationStr
                        graph_context = ToolObservationStr(obs, raw_context)

                    synthetic = create_recovery_synthetic_message(q)
                    messages.append({"role": "assistant", "content": synthetic})
                    messages.append({"role": "user", "content": f"Observation:\n{obs}"})

                    steps.append({
                        "iteration": iteration,
                        "type": "recovery_forced_graphrag",
                        "reason": last_err,
                        "observation_chars": len(obs),
                    })
                    errors.append(f"react-parse recovered (iter 1): {last_err}")
                    continue

                if _recovery_enabled() and iteration > 1 and graph_context.strip():
                    # Try to extract answer from malformed output
                    fb = self.parser.extract_fallback_answer(assistant_text)
                    if fb:
                        errors.append(f"react-parse recovered loose (iter {iteration}): {last_err}")
                        steps.append({
                            "iteration": iteration,
                            "type": "finish_recovery_loose",
                            "preview": fb[:200],
                        })
                        return _build_result_bundle(
                            q, fb.strip(), graph_context, steps, errors,
                            drug_image_urls, retrieval_hits
                        )

                errors.append(f"react-parse: {last_err}")
                return _build_result_bundle(
                    q,
                    "Không phân tích được định dạng ReAct sau nhiều lần thử.",
                    graph_context,
                    steps,
                    errors,
                    drug_image_urls,
                    retrieval_hits,
                )

            # Process successful parse
            result = self.parser.parse(assistant_text)

            if result.kind == "finish":
                if _want_agent_terminal_log():
                    preview = (result.answer or "")[:180] + "…" if len(result.answer or "") > 180 else ""
                    logger.info("ReAct iter=%s: Final Answer (no tool), preview=%r", iteration, preview)

                steps.append({
                    "iteration": iteration,
                    "type": "finish",
                    "preview": (result.answer or "")[:200],
                })
                return _build_result_bundle(
                    q, result.answer or "", graph_context, steps, errors,
                    drug_image_urls, retrieval_hits
                )

            if result.kind == "action":
                action_input = (result.input_text or "").strip()
                current_signature = (result.action or "", action_input.casefold())
                if (
                    graph_context.strip()
                    and result.action == "graphrag_query"
                    and last_action_signature == current_signature
                ):
                    forced_answer = _forced_finalize_answer(q, graph_context)
                    final_answer = _append_answer_source_note(forced_answer, graph_context, retrieval_hits)
                    errors.append("react-loop-guard: repeated graphrag action detected")
                    steps.append({
                        "iteration": iteration,
                        "type": "finish_loop_guard",
                        "tool": result.action,
                        "action_input_preview": action_input[:300],
                    })
                    return _build_result_bundle(
                        q, forced_answer, graph_context, steps, errors,
                        drug_image_urls, retrieval_hits
                    )

                if _want_agent_terminal_log():
                    inp = (result.input_text or "")[:240] + "…" if len(result.input_text or "") > 240 else ""
                    logger.info("ReAct iter=%s: call %s, action_input=%r", iteration, result.action, inp)

                obs, urls, hits = self._execute_tool(
                    result.action,
                    result.input_text,
                    q,
                    graph_context,
                    drug_image_urls,
                )
                retrieval_hits = merge_retrieval_hits(retrieval_hits, hits)
                drug_image_urls = urls

                if obs.strip():
                    graph_context = obs

                steps.append({
                    "iteration": iteration,
                    "type": "tool",
                    "tool": result.action,
                    "action_input_preview": (result.input_text or "")[:300],
                    "observation_chars": len(obs),
                })
                last_action_signature = current_signature

                messages.append({"role": "assistant", "content": assistant_text})
                reminder = "\n\n---\nReminder: Bạn đang ở trong quy trình ReAct. Dựa vào Observation trên, hãy tiếp tục bằng cách viết 'Thought:' và 'Final Answer:' để trả lời trực tiếp cho người dùng. Tuyệt đối không được viết tiếp hoặc lặp lại định dạng câu hỏi/trả lời của Observation."
                messages.append({"role": "user", "content": f"Observation:\n{obs}{reminder}"})
                continue

            # Error case
            errors.append(f"{result.kind}: {result.error_message}")
            return _build_result_bundle(
                q, "Lỗi luồng ReAct.", graph_context, steps, errors,
                drug_image_urls, retrieval_hits
            )

        # Max iterations reached
        errors.append("react: exceeded max_iterations")
        return _build_result_bundle(
            q,
            "Đã dùng hết số bước suy luận cho phép. Vui lòng thu hẹp câu hỏi hoặc thử lại.",
            graph_context,
            steps,
            errors,
            drug_image_urls,
            retrieval_hits,
        )

    def run_stream(self, question: str, history: list[dict[str, str]] | None = None) -> Iterator[dict[str, Any]]:
        """Execute ReAct agent with streaming events.
        
        Yields events for real-time UI updates:
        - step: New iteration started
        - reasoning_delta: Token from LLM
        - parse_retry: Retrying parse
        - tool: Tool execution started
        - tool_done: Tool execution completed
        - recovery_forced_graphrag: Recovery mode activated
        - answer_delta: Final answer chunk
        - done: Complete result bundle
        - error: Error occurred
        
        Args:
            question: User question to answer
            history: Previous conversation turns
            
        Yields:
            Event dictionaries with type and data
        """
        q = (question or "").strip()
        messages, clean_history = self._create_initial_messages(q, history)
        history_len = len(clean_history)

        errors: list[str] = []
        steps: list[dict[str, Any]] = []
        graph_context = ""
        drug_image_urls: list[str] = []
        retrieval_hits: list[dict[str, Any]] = []
        last_action_signature: tuple[str, str] | None = None

        for iteration in range(1, self.max_iterations + 1):
            yield {"event": "step", "iteration": iteration}

            assistant_text = ""
            last_parse_err = ""
            stream_buf = None

            for attempt in range(self.parse_retries):
                parts: list[str] = []
                from agent.react.stream_buffer import ReActStreamBuffer
                stream_buf = ReActStreamBuffer()

                try:
                    # Stream tokens from LLM
                    for chunk in self.llm.chat_stream(
                        messages=[
                            {"role": "system", "content": self.system_prompt},
                            *clean_history,
                            {"role": "user", "content": f"Question: {q}"},
                            *messages[2 + history_len:],
                        ],
                        temperature=0.15,
                        stop=["Observation:"],
                    ):
                        parts.append(chunk)
                        for event in stream_buf.feed(chunk):
                            yield event

                    # Flush remaining buffer
                    for event in stream_buf.finalize():
                        yield event

                    assistant_text = "".join(parts).strip()

                except LLMBackendError as exc:
                    errors.append(f"LLM: {exc}")
                    yield {"event": "error", "message": str(exc)}
                    bundle = _build_result_bundle(
                        q,
                        "Không thể kết nối mô hình. Vui lòng thử lại sau.",
                        graph_context,
                        steps,
                        errors,
                        drug_image_urls,
                        retrieval_hits,
                    )
                    yield {"event": "done", **bundle}
                    return

                result = self.parser.parse(assistant_text)
                if result.kind != "error":
                    break

                last_parse_err = result.error_message or "parse"
                if _want_agent_terminal_log():
                    logger.warning(
                        "ReAct stream parse error iter=%s attempt=%s: %s | raw=%r",
                        iteration,
                        attempt + 1,
                        last_parse_err,
                        assistant_text[:500] + "…" if len(assistant_text) > 500 else assistant_text,
                    )

                messages.append({"role": "assistant", "content": assistant_text})
                messages.append({"role": "user", "content": get_parse_retry_prompt(last_parse_err)})
                yield {"event": "parse_retry", "attempt": attempt + 1}

            else:
                # All retries exhausted
                last_err = last_parse_err or "parse"

                if _recovery_enabled() and iteration == 1 and not graph_context.strip():
                    # Recovery mode
                    obs, hits = run_graphrag_tool(q, q)
                    raw_context = getattr(obs, "raw_context", obs)
                    retrieval_hits = merge_retrieval_hits(retrieval_hits, hits)
                    obs, drug_image_urls = merge_pill_observation(q, obs, drug_image_urls)

                    if obs.strip():
                        from agent.react.tools import ToolObservationStr
                        graph_context = ToolObservationStr(obs, raw_context)

                    synthetic = create_recovery_synthetic_message(q)
                    messages.append({"role": "assistant", "content": synthetic})
                    messages.append({"role": "user", "content": f"Observation:\n{obs}"})

                    steps.append({
                        "iteration": iteration,
                        "type": "recovery_forced_graphrag",
                        "reason": last_err,
                        "observation_chars": len(obs),
                    })
                    errors.append(f"react-parse recovered (iter 1): {last_err}")

                    yield {"event": "tool", "name": "graphrag_query", "input": q[:800] + "…" if len(q) > 800 else q}
                    yield {"event": "tool_done", "observation_chars": len(obs), "recovery": True}
                    yield {
                        "event": "recovery_forced_graphrag",
                        "observation_chars": len(obs),
                        "reason": last_err,
                    }
                    continue

                if _recovery_enabled() and iteration > 1 and graph_context.strip():
                    fb = self.parser.extract_fallback_answer(assistant_text)
                    if fb:
                        errors.append(f"react-parse recovered loose (iter {iteration}): {last_err}")
                        steps.append({
                            "iteration": iteration,
                            "type": "finish_recovery_loose",
                            "preview": fb[:200],
                        })
                        final_answer = _append_answer_source_note(fb.strip(), graph_context, retrieval_hits)
                        yield {"event": "reasoning_end"}
                        yield {"event": "answer_start"}
                        for piece in _chunk_stream_answer(final_answer):
                            yield {"event": "answer_delta", "text": piece}
                        bundle = _build_result_bundle(
                            q, final_answer, graph_context, steps, errors,
                            drug_image_urls, retrieval_hits
                        )
                        yield {"event": "done", **bundle}
                        return

                errors.append(f"react-parse: {last_err}")
                bundle = _build_result_bundle(
                    q,
                    "Không phân tích được định dạng ReAct sau nhiều lần thử.",
                    graph_context,
                    steps,
                    errors,
                    drug_image_urls,
                    retrieval_hits,
                )
                yield {"event": "done", **bundle}
                return

            # Process successful result
            result = self.parser.parse(assistant_text)

            if result.kind == "finish":
                if _want_agent_terminal_log():
                    preview = (result.answer or "")[:180] + "…" if len(result.answer or "") > 180 else ""
                    logger.info("ReAct stream iter=%s: Final Answer, preview=%r", iteration, preview)

                steps.append({
                    "iteration": iteration,
                    "type": "finish",
                    "preview": (result.answer or "")[:200],
                })
                final_answer = _append_answer_source_note(
                    (result.answer or "").strip(),
                    graph_context,
                    retrieval_hits,
                )
                if stream_buf and stream_buf.has_final_answer:
                    # The main answer part was already streamed on the fly.
                    # We only stream the appended source note extra text if present.
                    ans_strip = (result.answer or "").strip()
                    if final_answer.startswith(ans_strip):
                        extra = final_answer[len(ans_strip):]
                        if extra:
                            for piece in _chunk_stream_answer(extra):
                                yield {"event": "answer_delta", "text": piece}
                else:
                    yield {"event": "reasoning_end"}
                    yield {"event": "answer_start"}
                    for piece in _chunk_stream_answer(final_answer):
                        yield {"event": "answer_delta", "text": piece}
                bundle = _build_result_bundle(
                    q, final_answer, graph_context, steps, errors,
                    drug_image_urls, retrieval_hits
                )
                yield {"event": "done", **bundle}
                return

            if result.kind == "action":
                action_input = (result.input_text or "").strip()
                current_signature = (result.action or "", action_input.casefold())
                if (
                    graph_context.strip()
                    and result.action == "graphrag_query"
                    and last_action_signature == current_signature
                ):
                    forced_answer = _forced_finalize_answer(q, graph_context)
                    final_answer = _append_answer_source_note(forced_answer, graph_context, retrieval_hits)
                    errors.append("react-loop-guard: repeated graphrag action detected")
                    steps.append({
                        "iteration": iteration,
                        "type": "finish_loop_guard",
                        "tool": result.action,
                        "action_input_preview": action_input[:300],
                    })
                    yield {"event": "reasoning_end"}
                    yield {"event": "answer_start"}
                    for piece in _chunk_stream_answer(final_answer):
                        yield {"event": "answer_delta", "text": piece}
                    bundle = _build_result_bundle(
                        q, final_answer, graph_context, steps, errors,
                        drug_image_urls, retrieval_hits
                    )
                    yield {"event": "done", **bundle}
                    return

                yield {"event": "tool", "name": result.action, "input": (result.input_text or "")[:800]}

                if _want_agent_terminal_log():
                    inp = (result.input_text or "")[:240] + "…" if len(result.input_text or "") > 240 else ""
                    logger.info("ReAct stream iter=%s: call %s, action_input=%r", iteration, result.action, inp)

                obs, urls, hits = self._execute_tool(
                    result.action,
                    result.input_text,
                    q,
                    graph_context,
                    drug_image_urls,
                )
                retrieval_hits = merge_retrieval_hits(retrieval_hits, hits)
                drug_image_urls = urls

                if obs.strip():
                    graph_context = obs

                steps.append({
                    "iteration": iteration,
                    "type": "tool",
                    "tool": result.action,
                    "action_input_preview": (result.input_text or "")[:300],
                    "observation_chars": len(obs),
                })
                last_action_signature = current_signature

                yield {"event": "tool_done", "observation_chars": len(obs)}
                messages.append({"role": "assistant", "content": assistant_text})
                reminder = "\n\n---\nReminder: Bạn đang ở trong quy trình ReAct. Dựa vào Observation trên, hãy tiếp tục bằng cách viết 'Thought:' và 'Final Answer:' để trả lời trực tiếp cho người dùng. Tuyệt đối không được viết tiếp hoặc lặp lại định dạng câu hỏi/trả lời của Observation."
                messages.append({"role": "user", "content": f"Observation:\n{obs}{reminder}"})
                continue

            errors.append(f"{result.kind}: {result.error_message}")
            bundle = _build_result_bundle(
                q, "Lỗi luồng ReAct.", graph_context, steps, errors,
                drug_image_urls, retrieval_hits
            )
            yield {"event": "done", **bundle}
            return

        # Max iterations
        errors.append("react: exceeded max_iterations")
        bundle = _build_result_bundle(
            q,
            "Đã dùng hết số bước suy luận cho phép.",
            graph_context,
            steps,
            errors,
            drug_image_urls,
            retrieval_hits,
        )
        yield {"event": "done", **bundle}


# Convenience functions for backward compatibility

def run_react_agent(
    question: str,
    *,
    ollama_model: str | None = None,
    ollama_host: str | None = None,
    ollama_timeout: int = 120,
    max_iterations: int | None = None,
    parse_max_retries: int | None = None,
) -> dict[str, Any]:
    """Run ReAct agent synchronously (backward compatible)."""
    settings = get_settings()
    host = ollama_host or settings.ollama.host
    agent = ReActAgent(
        llm_backend=OllamaBackend(host=host, timeout=ollama_timeout),
        max_iterations=max_iterations,
        parse_retries=parse_max_retries,
    )
    return agent.run_sync(question)


def run_react_agent_event_stream(
    question: str,
    *,
    ollama_model: str | None = None,
    ollama_host: str | None = None,
    ollama_timeout: int = 120,
    max_iterations: int | None = None,
    parse_max_retries: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Run ReAct agent with streaming (backward compatible)."""
    settings = get_settings()
    host = ollama_host or settings.ollama.host
    agent = ReActAgent(
        llm_backend=OllamaBackend(host=host, timeout=ollama_timeout),
        max_iterations=max_iterations,
        parse_retries=parse_max_retries,
    )
    return agent.run_stream(question)
