"""Agent y tế (DATN): **mặc định ReAct** (``react_agent``) + tool ``graphrag_query``. Pipeline router/orchestrator là **legacy**.

**Mặc định (API / UI)**

- ``POST /api/agent-query``: ReAct trừ khi ``use_legacy_pipeline: true`` hoặc ``use_react: false`` hoặc env ``AGENT_USE_LEGACY_PIPELINE=1`` / ``AGENT_USE_REACT=0``.

**Thành phần**

- ``react_agent``: luồng chính — Thought / Action / Observation + ``graphrag_query``.
- ``tools``: ``tool_graphrag_query``.
- ``orchestrator`` / ``langgraph_app`` / ``router``: **legacy** (router + GraphRAG + Ollama một pass hoặc LangGraph).
- ``medication_tools``: gắn pipeline legacy; chưa tích hợp ReAct dưới dạng tool riêng.

**Chạy**

- ``agent.orchestrator.run_agent_demo``
- ``agent.langgraph_app.run_agent_demo_langgraph`` — ``python -m agent --langgraph ...``

Từ gốc repo: ``python -m agent --question "..."``

"""
from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
