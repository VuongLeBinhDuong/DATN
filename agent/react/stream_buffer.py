"""ReAct LLM output streaming buffer.

Accumulates chunks in real-time to prevent streaming Final Answer text as reasoning.
"""

from __future__ import annotations

import re
from typing import Any


class ReActStreamBuffer:
    """Helper to buffer and filter ReAct LLM stream output in real-time.
    
    Accumulates streaming chunks and determines whether they belong to
    the reasoning (Thought) phase or final answer (Final Answer) phase.
    
    If 'Final Answer:' is matched:
    - Streams any remaining reasoning chunks before the match.
    - Yields 'reasoning_end' and 'answer_start'.
    - Suppresses further chunks from being streamed as 'reasoning_delta'.
    """

    def __init__(self) -> None:
        self.buffer = ""
        self.has_final_answer = False
        self.streamed_pos = 0
        self.emitted_transition = False

    def feed(self, chunk: str) -> list[dict[str, Any]]:
        """Feed a new streaming chunk from the LLM.
        
        Returns:
            List of event dicts to be yielded by the agent.
        """
        self.buffer += chunk
        events = []

        if not self.has_final_answer:
            # Look for Final Answer marker (case-insensitive, optionally with stars)
            match = re.search(r"\*?\*?Final\s+Answer\*?\*?\s*:\s*", self.buffer, re.IGNORECASE)
            
            if match:
                self.has_final_answer = True
                start, end = match.span()
                
                # Extract and stream any pending reasoning text before 'Final Answer:'
                thought_part = self.buffer[self.streamed_pos:start]
                if thought_part:
                    events.append({"event": "reasoning_delta", "text": thought_part})
                
                # Signal transition in UI
                events.append({"event": "reasoning_end"})
                events.append({"event": "answer_start"})
                self.emitted_transition = True
                self.streamed_pos = end
            else:
                # Keep a safety buffer of 20 characters to avoid streaming
                # partial "Final Answer:" (e.g. if the chunk ends with "Final An")
                safe_len = len(self.buffer) - 20
                if safe_len > self.streamed_pos:
                    text_to_stream = self.buffer[self.streamed_pos:safe_len]
                    events.append({"event": "reasoning_delta", "text": text_to_stream})
                    self.streamed_pos = safe_len
        
        return events

    def finalize(self) -> list[dict[str, Any]]:
        """Flush any remaining text in the buffer at the end of the LLM stream.
        
        Returns:
            List of event dicts.
        """
        events = []
        if self.streamed_pos < len(self.buffer):
            remaining = self.buffer[self.streamed_pos:]
            if not self.has_final_answer:
                # If Final Answer was never matched, stream the rest as reasoning_delta
                events.append({"event": "reasoning_delta", "text": remaining})
            self.streamed_pos = len(self.buffer)
        return events
