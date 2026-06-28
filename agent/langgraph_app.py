"""[LEGACY — giữ để so sánh / rollback]

Cùng logic ``orchestrator.py`` nhưng ``StateGraph`` (router → graphrag → synthesize).
Chỉ dùng khi bật pipeline legacy **và** ``use_langgraph`` hoặc ``AGENT_USE_LANGGRAPH=1``.
Mặc định hệ thống dùng ``react_agent``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests
from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from agent.medication_tools import (
    build_medication_plan,
    build_reminder_events,
    extract_drug_info_from_collection_context,
    parse_medication_intent,
    render_medication_context,
)
from agent.router import plan_retrieval
from agent.tools import augment_sources_for_ui, merge_context_blocks, tool_graphrag_query
from core.settings import get_settings
from llm_pipeline.rag_llm import DEFAULT_AGENT_MERGED_PROMPT, SOCIAL_TURN_PROMPT, answer_with_ollama


class AgentState(TypedDict, total=False):
    question: str
    strategy: str
    ollama_model: str
    router_model: str
    ollama_host: str
    ollama_timeout: int
    plan: dict[str, Any]
    graph_text: str
    med_text: str
    hits: list[dict[str, Any]]
    drug_images: list[str]
    medication_plan: list[dict[str, Any]]
    reminders: list[dict[str, Any]]
    errors: list[str]
    answer: str


def _err(state: AgentState, msg: str) -> list[str]:
    return list(state.get("errors") or []) + [msg]


def build_router_node():
    def router_node(state: AgentState) -> dict[str, Any]:
        q = state.get("question") or ""
        strategy = state.get("strategy") or "auto"
        settings = get_settings()
        p = plan_retrieval(
            q,
            strategy=strategy,
            ollama_model=state.get("ollama_model") or settings.ollama.model,
            router_model=state.get("router_model"),
            ollama_host=state.get("ollama_host") or settings.ollama.host,
            ollama_timeout=int(state.get("ollama_timeout") or 120),
        )
        pl: dict[str, Any] = {
            "use_graphrag": p.use_graphrag,
            "reason": p.reason,
        }
        if p.router_route is not None:
            pl["router_route"] = p.router_route
        if p.next_pipeline is not None:
            pl["next_pipeline"] = p.next_pipeline
        return {"plan": pl}

    return router_node


def build_graphrag_node():
    def graphrag_node(state: AgentState) -> dict[str, Any]:
        plan = state.get("plan") or {}
        if not plan.get("use_graphrag"):
            return {"graph_text": ""}
        q = state.get("question") or ""
        try:
            return {"graph_text": tool_graphrag_query(q)}
        except Exception as exc:  # noqa: BLE001
            return {"graph_text": "", "errors": _err(state, f"GraphRAG: {exc}")}

    return graphrag_node


def build_synthesize_node():
    def synthesize_node(state: AgentState) -> dict[str, Any]:
        q = state.get("question") or ""
        graph_text = state.get("graph_text") or ""
        hits = list(state.get("hits") or [])
        med_text = ""
        drug_images: list[str] = []
        medication_plan: list[dict[str, Any]] = []
        reminders: list[dict[str, Any]] = []
        extra_errors: list[str] = []
        med_intent = parse_medication_intent(q)
        if med_intent.needs_drug_info or med_intent.needs_plan or med_intent.needs_reminders:
            drug_name = med_intent.drug_name or "thuốc theo đơn"
            if not graph_text:
                try:
                    graph_text = tool_graphrag_query(q)
                except Exception as exc:  # noqa: BLE001
                    return {
                        "errors": _err(state, f"GraphRAG: {exc}"),
                        "answer": "",
                        "hits": hits,
                        "med_text": "",
                        "drug_images": [],
                        "medication_plan": [],
                        "reminders": [],
                    }
            info: dict[str, Any] = {}
            if med_intent.needs_drug_info:
                info = extract_drug_info_from_collection_context(drug_name, graph_text)
                for src in info.get("sources") or []:
                    hits.append(src)
                drug_images = list(info.get("images") or [])
                for err in info.get("errors") or []:
                    extra_errors.append(f"DrugLookup: {err}")
            if med_intent.needs_plan:
                medication_plan = build_medication_plan(
                    drug_name,
                    doses_per_day=med_intent.doses_per_day or 2,
                    days=med_intent.days or 7,
                )
            if med_intent.needs_reminders:
                reminders = build_reminder_events(medication_plan)
            med_text = render_medication_context(info, medication_plan, reminders)
        merged = merge_context_blocks(graph_text)
        err_updates: list[str] = list(state.get("errors") or [])
        err_updates.extend(extra_errors)
        if med_text:
            merged = merged + "\n\n" + med_text if merged else med_text
        grounded = bool((graph_text or "").strip()) or bool((med_text or "").strip())
        plan_cur = state.get("plan") or {}
        route = str(plan_cur.get("router_route") or "")
        if grounded:
            synth_basename: str | None = DEFAULT_AGENT_MERGED_PROMPT
        else:
            synth_basename = SOCIAL_TURN_PROMPT if route == "social" else None
        ollama_model = state.get("ollama_model") or "llama3.2:3b"
        ollama_host = state.get("ollama_host") or "http://localhost:11434"
        timeout = int(state.get("ollama_timeout") or 120)
        try:
            final = answer_with_ollama(
                q,
                merged,
                ollama_model,
                ollama_host,
                timeout,
                grounded=grounded,
                prompt_basename=synth_basename,
            )
        except requests.RequestException as exc:
            err_updates.append(f"Ollama: {exc}")
            final = "Không thể kết nối mô hình trả lời. Vui lòng thử lại sau."

        plan_out = dict(plan_cur)
        plan_out["llm_grounded"] = grounded

        return {
            "answer": final,
            "hits": hits,
            "med_text": med_text,
            "drug_images": drug_images,
            "medication_plan": medication_plan,
            "reminders": reminders,
            "errors": err_updates,
            "plan": plan_out,
        }

    return synthesize_node


def build_medical_agent_graph():
    """Linear graph: router → graphrag → synthesize → END."""
    g = StateGraph(AgentState)
    g.add_node("router", build_router_node())
    g.add_node("graphrag", build_graphrag_node())
    g.add_node("synthesize", build_synthesize_node())
    g.add_edge(START, "router")
    g.add_edge("router", "graphrag")
    g.add_edge("graphrag", "synthesize")
    g.add_edge("synthesize", END)
    return g.compile()


def run_agent_demo_langgraph(
    question: str,
    *,
    strategy: str = "auto",
    config_path: Path | None = None,
    ollama_model: str | None = None,
    router_model: str | None = None,
    ollama_host: str | None = None,
    ollama_timeout: int = 120,
) -> dict[str, Any]:
    """Same return shape as agent_demo.orchestrator.run_agent_demo."""
    _ = config_path
    settings = get_settings()
    _model = ollama_model or settings.ollama.model
    _host = ollama_host or settings.ollama.host
    graph = build_medical_agent_graph()
    initial: AgentState = {
        "question": question,
        "strategy": strategy,
        "ollama_model": _model,
        "router_model": router_model,
        "ollama_host": _host,
        "ollama_timeout": ollama_timeout,
        "errors": [],
    }
    out = graph.invoke(initial)
    graph_full = out.get("graph_text") or ""
    hits = list(out.get("hits") or [])
    sources = [
        {
            "title": h.get("title"),
            "link": h.get("link"),
            "source": h.get("source"),
            "score": float(h["score"]) if h.get("score") is not None else None,
        }
        for h in augment_sources_for_ui(hits, graph_full)
    ]
    return {
        "question": question,
        "strategy": strategy,
        "plan": out.get("plan") or {},
        "context_graphrag_preview": graph_full[:2000] + ("…" if len(graph_full) > 2000 else ""),
        "context_graphrag_full": graph_full[:48000] + ("… [đã cắt]" if len(graph_full) > 48000 else ""),
        "context_graphrag_total_chars": len(graph_full),
        "context_medication_preview": (out.get("med_text") or "")[:2000]
        + ("…" if len(out.get("med_text") or "") > 2000 else ""),
        "sources": sources,
        "drug_images": list(out.get("drug_images") or []),
        "medication_plan": list(out.get("medication_plan") or []),
        "reminders": list(out.get("reminders") or []),
        "answer": out.get("answer") or "",
        "errors": out.get("errors") or [],
    }
