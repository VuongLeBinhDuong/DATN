"""[LEGACY — giữ để so sánh / rollback]

Pipeline router + GraphRAG + Ollama (không ReAct). Mặc định API/UI dùng ``react_agent.run_react_agent``;
chỉ chạy module này khi ``use_legacy_pipeline`` hoặc env ``AGENT_USE_LEGACY_PIPELINE=1`` (xem ``llm_pipeline.app``).

Luồng: ``plan_retrieval`` (auto: social | graphrag) → ``tool_graphrag_query`` nếu cần → tổng hợp prompt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from agent.medication_tools import (
    build_medication_plan,
    build_reminder_events,
    extract_drug_info_from_collection_context,
    parse_medication_intent,
    render_medication_context,
)
from agent.router import plan_retrieval
from agent.tools import augment_sources_for_ui, merge_context_blocks, tool_graphrag_query
from llm_pipeline.rag_llm import DEFAULT_AGENT_MERGED_PROMPT, SOCIAL_TURN_PROMPT, answer_with_ollama
from core.settings import get_settings


def run_agent_demo(
    question: str,
    *,
    strategy: str = "auto",
    config_path: Path | None = None,
    ollama_model: str | None = None,
    router_model: str | None = None,
    ollama_host: str | None = None,
    ollama_timeout: int = 120,
) -> dict[str, Any]:
    """
    Returns a trace dict: plan, partial contexts, final answer, errors.
    """
    _ = config_path
    settings = get_settings()
    _model = ollama_model or settings.ollama.model
    _host = ollama_host or settings.ollama.host

    plan = plan_retrieval(
        question,
        strategy=strategy,
        ollama_model=_model,
        router_model=router_model,
        ollama_host=_host,
        ollama_timeout=ollama_timeout,
    )
    graph_text = ""
    med_text = ""
    hits: list[dict[str, Any]] = []
    medication_plan: list[dict[str, Any]] = []
    reminders: list[dict[str, Any]] = []
    drug_images: list[str] = []
    drug_info = {}
    errors: list[str] = []

    if plan.use_graphrag:
        try:
            graph_text = tool_graphrag_query(question)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"GraphRAG: {exc}")
            graph_text = ""

    med_intent = parse_medication_intent(question)
    if med_intent.needs_drug_info or med_intent.needs_plan or med_intent.needs_reminders:
        drug_name = med_intent.drug_name or "thuốc theo đơn"
        # Enforce medication info retrieval through GraphRAG collection context.
        if not graph_text:
            try:
                graph_text = tool_graphrag_query(question)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"GraphRAG: {exc}")
        if med_intent.needs_drug_info:
            drug_info = extract_drug_info_from_collection_context(drug_name, graph_text)
            drug_images = list(drug_info.get("images") or [])
            for src in drug_info.get("sources") or []:
                hits.append(src)
            for err in drug_info.get("errors") or []:
                errors.append(f"DrugLookup: {err}")
        if med_intent.needs_plan:
            medication_plan = build_medication_plan(
                drug_name,
                doses_per_day=med_intent.doses_per_day or 2,
                days=med_intent.days or 7,
            )
        if med_intent.needs_reminders:
            reminders = build_reminder_events(medication_plan)
        med_text = render_medication_context(drug_info, medication_plan, reminders)

    merged = merge_context_blocks(graph_text)
    if med_text:
        merged = merged + "\n\n" + med_text if merged else med_text

    grounded = bool((graph_text or "").strip()) or bool((med_text or "").strip())

    if grounded:
        synth_basename: str | None = DEFAULT_AGENT_MERGED_PROMPT
    else:
        synth_basename = SOCIAL_TURN_PROMPT if plan.router_route == "social" else None

    try:
        final = answer_with_ollama(
            question,
            merged,
            ollama_model,
            ollama_host,
            ollama_timeout,
            grounded=grounded,
            prompt_basename=synth_basename,
        )
    except requests.RequestException as exc:
        errors.append(f"Ollama: {exc}")
        final = "Không thể kết nối mô hình trả lời. Vui lòng thử lại sau."

    sources = [
        {
            "title": h.get("title"),
            "link": h.get("link"),
            "source": h.get("source"),
            "score": float(h["score"]) if h.get("score") is not None else None,
        }
        for h in augment_sources_for_ui(hits, graph_text)
    ]

    return {
        "question": question,
        "strategy": strategy,
        "plan": {
            "use_graphrag": plan.use_graphrag,
            "reason": plan.reason,
            "llm_grounded": grounded,
            **(
                {
                    "router_route": plan.router_route,
                    "next_pipeline": plan.next_pipeline,
                }
                if plan.router_route is not None or plan.next_pipeline is not None
                else {}
            ),
        },
        "context_graphrag_preview": graph_text[:2000] + ("…" if len(graph_text) > 2000 else ""),
        "context_graphrag_full": graph_text[:48000] + ("… [đã cắt]" if len(graph_text) > 48000 else ""),
        "context_graphrag_total_chars": len(graph_text),
        "context_medication_preview": med_text[:2000] + ("…" if len(med_text) > 2000 else ""),
        "sources": sources,
        "drug_images": drug_images,
        "medication_plan": medication_plan,
        "reminders": reminders,
        "answer": final,
        "errors": errors,
    }
