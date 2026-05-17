"""ReAct agent module - split into focused submodules.

This module refactors the monolithic react_agent.py (752 lines) into:
- parser.py: ReAct output parsing
- tools.py: Tool execution (graphrag, pill_image_lookup)
- agent.py: Main ReAct loop (sync and streaming)
"""

from __future__ import annotations

from agent.react.agent import ReActAgent, run_react_agent, run_react_agent_event_stream
from agent.react.parser import ReActParseResult, ReActParser

__all__ = [
    "ReActAgent",
    "ReActParser",
    "ReActParseResult",
    "run_react_agent",
    "run_react_agent_event_stream",
]
