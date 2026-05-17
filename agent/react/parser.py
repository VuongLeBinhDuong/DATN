"""ReAct output parsing utilities.

Extracts structured data from LLM responses following ReAct pattern:
Thought -> Action -> Action Input -> Observation -> Final Answer
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

# Regex patterns for parsing ReAct output
FINAL_ANSWER_LINE = re.compile(
    r"(?m)^\s*\*{0,2}\s*Final\s+Answer\s*\*{0,2}\s*:\s*",
    re.IGNORECASE,
)
ACTION_BLOCK = re.compile(
    r"Action\s*\d*\s*:\s*(.+?)\s*Action\s*\d*\s*Input\s*\d*\s*:\s*(.+?)(?=\s*(?:Observation\s*:|$))",
    re.DOTALL | re.IGNORECASE,
)
FALLBACK_ACTION_INPUT = re.compile(
    r"Action\s*Input\s*\d*\s*:\s*(.+?)(?=\s*(?:Observation\s*:|$))",
    re.DOTALL | re.IGNORECASE,
)

# Tool name normalization map
TOOL_ALIASES = {
    "graphrag": "graphrag_query",
    "graph_rag": "graphrag_query",
    "pill_image": "pill_image_lookup",
    "pill_images": "pill_image_lookup",
    "pill_lookup": "pill_image_lookup",
    "pill_image_look_up": "pill_image_lookup",
}

ALLOWED_TOOLS = frozenset({"graphrag_query", "pill_image_lookup"})


@dataclass(frozen=True)
class ReActParseResult:
    """Structured result from parsing ReAct output."""

    kind: Literal["action", "finish", "error"]
    action: str | None = None  # Tool name (if kind == "action")
    input_text: str | None = None  # Tool input (if kind == "action")
    answer: str | None = None  # Final answer (if kind == "finish")
    error_message: str | None = None  # Error description (if kind == "error")


class ReActParser:
    """Parser for ReAct-style LLM outputs.
    
    Handles markdown normalization and extracts structured actions.
    """

    @staticmethod
    def _normalize_markdown(text: str) -> str:
        """Remove markdown bold wrapping from ReAct labels.
        
        Models often output **Action:** which breaks regex matching.
        """
        t = text or ""
        for label in ("Thought", "Action", "Action Input", "Final Answer", "Observation"):
            # **Label:** or **Label :** -> Label:
            t = re.sub(
                rf"\*\*\s*{label}\s*:\s*\*\*",
                f"{label}:",
                t,
                flags=re.IGNORECASE,
            )
            t = re.sub(rf"\*\*{label}\s*:\*\*", f"{label}:", t, flags=re.IGNORECASE)

        # Handle **Final Answer** on its own line without colon
        t = re.sub(
            r"(?m)^(\s*)\*{1,2}\s*Final\s+Answer\s*\*{1,2}\s*$",
            r"\1Final Answer:",
            t,
            flags=re.IGNORECASE,
        )
        t = re.sub(
            r"(?m)^(\s*)Final\s+Answer\s*$",
            r"\1Final Answer:",
            t,
            flags=re.IGNORECASE,
        )
        return t

    @staticmethod
    def _strip_tool_noise(name: str) -> str:
        """Clean tool name from markdown artifacts.
        
        Preserves underscores - "graphrag_query" must stay intact.
        """
        return re.sub(r"[\*`]+", "", (name or "")).strip().lower().replace(" ", "_")

    def parse(self, text: str) -> ReActParseResult:
        """Parse ReAct output and return structured result.
        
        Args:
            text: Raw LLM output to parse
            
        Returns:
            ReActParseResult with kind and extracted data
        """
        raw = self._normalize_markdown((text or "").strip())
        if not raw:
            return ReActParseResult(kind="error", error_message="Empty response")

        final_matches = list(FINAL_ANSWER_LINE.finditer(raw))
        has_final = bool(final_matches)
        action_match = ACTION_BLOCK.search(raw)

        # Check for conflicting action + final answer
        if action_match and has_final:
            first_final_pos = final_matches[0].start()
            if first_final_pos >= action_match.start():
                return ReActParseResult(
                    kind="error",
                    error_message="Both Action and Final Answer present - choose one",
                )
            has_final = False

        # Extract action
        if action_match:
            name = self._strip_tool_noise(action_match.group(1))
            name = TOOL_ALIASES.get(name, name)
            input_text = action_match.group(2).strip().strip('"').strip("'")

            if name not in ALLOWED_TOOLS:
                return ReActParseResult(
                    kind="error",
                    error_message=f"Invalid tool: {name!r}. Allowed: {', '.join(sorted(ALLOWED_TOOLS))}",
                )
            return ReActParseResult(kind="action", action=name, input_text=input_text or None)

        # Extract final answer
        if has_final:
            parts = FINAL_ANSWER_LINE.split(raw, maxsplit=1)
            answer = parts[-1].strip() if len(parts) > 1 else ""
            if not answer:
                return ReActParseResult(
                    kind="error",
                    error_message="Missing content after Final Answer:",
                )
            return ReActParseResult(kind="finish", answer=answer)

        # Fallback: try to recover action input
        fallback_match = FALLBACK_ACTION_INPUT.search(raw)
        if fallback_match:
            if re.search(r"Action\s*\d*\s*:\s*[^\n]*graphrag", raw, re.I):
                return ReActParseResult(
                    kind="action",
                    action="graphrag_query",
                    input_text=fallback_match.group(1).strip().strip('"').strip("'") or None,
                )
            if re.search(r"Action\s*\d*\s*:\s*[^\n]*pill[_\s-]*image", raw, re.I):
                return ReActParseResult(
                    kind="action",
                    action="pill_image_lookup",
                    input_text=fallback_match.group(1).strip().strip('"').strip("'") or None,
                )

        return ReActParseResult(
            kind="error",
            error_message="Missing Action+Action Input or Final Answer",
        )

    def extract_fallback_answer(self, text: str) -> str | None:
        """Extract answer text when Final Answer label is malformed.
        
        Used for recovery when model produces answer without proper formatting.
        """
        t = self._normalize_markdown((text or "").strip())
        if len(t) < 25:
            return None

        parts = FINAL_ANSWER_LINE.split(t, maxsplit=1)
        if len(parts) > 1:
            body = parts[-1].strip()
            if body:
                return body

        # If contains action marker, it's not a standalone answer
        if re.search(r"(?m)^\s*Action\s*:\s*graphrag", t, re.IGNORECASE):
            return None

        return t
