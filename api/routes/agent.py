"""Agent/ReAct endpoints.

- POST /api/agent-query: Synchronous agent execution
- POST /api/agent-query/stream: Streaming agent execution (NDJSON)
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.dependencies import AgentServiceDep, SettingsDep, check_rate_limit
from core.settings import get_settings

router = APIRouter(prefix="/api", tags=["agent"])


class AgentQueryIn(BaseModel):
    """Request body for agent query."""
    message: str = Field(..., min_length=1, max_length=4000)
    strategy: str = Field(default="auto", pattern="^(auto|graph)$")
    backend: str = Field(default="auto", pattern="^(auto|ollama|openrouter)$", description="LLM backend to use")
    history: list[dict[str, str]] = Field(default=[], description="Previous conversation turns")


class SourceOut(BaseModel):
    """Source citation in response."""
    title: str | None = None
    link: str | None = None
    source: str | None = None
    score: float | None = None


class AgentQueryOut(BaseModel):
    """Full agent response with metadata."""
    answer: str
    strategy: str = "react"
    plan: dict = {}
    errors: list[str] = []
    sources: list[SourceOut] = []
    context_milvus_preview: str = ""
    context_graphrag_preview: str = ""
    context_graphrag_full: str = ""
    context_graphrag_total_chars: int = 0
    drug_images: list[str] = []
    medication_plan: list[dict] = []
    reminders: list[dict] = []


@router.post("/agent-query", response_model=AgentQueryOut)
async def api_agent_query(
    body: AgentQueryIn,
    service: AgentServiceDep,
    settings: SettingsDep,
    request: Request = None,
) -> AgentQueryOut:
    """Execute agent query with ReAct strategy."""
    check_rate_limit(request, settings)
    
    # Create service with selected backend if specified
    if body.backend != "auto":
        from core.llm_backends import get_llm_backend
        from services.agent_service import AgentService
        llm = get_llm_backend(backend=body.backend)
        service = AgentService(settings=settings, llm_backend=llm)
    
    result = service.execute(
        message=body.message,
        strategy=body.strategy,
        history=body.history,
    )
    
    return AgentQueryOut(**result)


@router.post("/agent-query/stream")
async def api_agent_query_stream(
    body: AgentQueryIn,
    service: AgentServiceDep,
    settings: SettingsDep,
    request: Request = None,
) -> StreamingResponse:
    """Stream agent execution events (NDJSON format)."""
    check_rate_limit(request, settings)
    
    # Create service with selected backend if specified
    if body.backend != "auto":
        from core.llm_backends import get_llm_backend
        from services.agent_service import AgentService
        llm = get_llm_backend(backend=body.backend)
        service = AgentService(settings=settings, llm_backend=llm)
    
    def ndjson_stream():
        """Generate NDJSON stream of events."""
        for event in service.execute_stream(body.message, body.strategy, history=body.history):
            yield json.dumps(event, ensure_ascii=False) + "\n"
    
    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class LangChainGraphQueryIn(BaseModel):
    """Request body for LangChain GraphRAG query."""
    message: str = Field(..., min_length=1, max_length=4000, description="Question to ask")


class LangChainGraphQueryOut(BaseModel):
    """Response from LangChain GraphRAG."""
    answer: str
    sources: list[SourceOut] = []
    context_preview: str = ""


@router.post("/langchain-graph-query", response_model=LangChainGraphQueryOut)
async def api_langchain_graph_query(
    body: LangChainGraphQueryIn,
    settings: SettingsDep,
    request: Request = None,
) -> LangChainGraphQueryOut:
    """Query using LangChain GraphRAG WITH LLM synthesis (disease/symptom/drug entity graph).
    
    This endpoint uses the Neo4j graph built by the notebook at
    `langchain_graphrag/medical_qa_graph.ipynb` and synthesizes answer via Ollama LLM.
    """
    check_rate_limit(request, settings)
    
    from services.retrieval_service import RetrievalService
    
    service = RetrievalService()
    answer, sources = await service.query_langchain_graph_with_sources(body.message)
    
    # Get context preview (first 500 chars)
    from llm_pipeline.langchain_graphrag import retrieve_langchain_graph_context
    context, _ = retrieve_langchain_graph_context(body.message)
    context_preview = context[:500] + "..." if len(context) > 500 else context
    
    return LangChainGraphQueryOut(
        answer=answer,
        sources=[SourceOut(**s) for s in sources],
        context_preview=context_preview,
    )


@router.post("/langchain-graph-query/direct", response_model=LangChainGraphQueryOut)
async def api_langchain_graph_query_direct(
    body: LangChainGraphQueryIn,
    settings: SettingsDep,
    request: Request = None,
) -> LangChainGraphQueryOut:
    """Query Neo4j DIRECTLY without LLM - return raw context only.
    
    **PRIORITY: Custom KG (123k entities)** → LangChain GraphRAG fallback
    
    This endpoint queries the CUSTOM KG first (your 123k entities with 
    CO_OCCURS_WITH relations). If no results, falls back to LangChain graph.
    
    Returns raw evidence chunks without LLM synthesis.
    """
    check_rate_limit(request, settings)
    
    # === PRIORITY 1: Custom KG (your 123k entities) ===
    from llm_pipeline.graphrag_query import _custom_kg_available, _run_custom_kg_query
    from llm_pipeline.neo4j_graphrag import load_neo4j_config
    
    neo_cfg = load_neo4j_config()
    
    if _custom_kg_available():
        raw_context, hits = _run_custom_kg_query(body.message, neo_cfg=neo_cfg)
        if raw_context.strip() and hits:
            return LangChainGraphQueryOut(
                answer=raw_context,
                sources=[SourceOut(
                    title=h.get("title", ""),
                    source=h.get("doc_id", ""),
                    score=h.get("score", 0.0),
                ) for h in hits],
                context_preview=raw_context[:200] + "..." if len(raw_context) > 200 else raw_context,
            )
    
    # === FALLBACK: LangChain GraphRAG ===
    from llm_pipeline.langchain_graphrag import run_langchain_graphrag_query_direct
    
    raw_context, sources = run_langchain_graphrag_query_direct(body.message)
    
    return LangChainGraphQueryOut(
        answer=raw_context,
        sources=[SourceOut(**s) for s in sources],
        context_preview=raw_context[:200] + "..." if len(raw_context) > 200 else raw_context,
    )
