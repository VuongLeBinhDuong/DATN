"""GraphRAG query endpoints.

- GET /ask: Simple query (for quick testing)
- POST /api/query: Full query with sources
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.dependencies import KnowledgeRepoDep, SettingsDep, check_rate_limit

router = APIRouter(tags=["graphrag"])


class QueryIn(BaseModel):
    """Request body for GraphRAG query."""
    message: str = Field(..., min_length=1, max_length=4000)


class SourceOut(BaseModel):
    """Source citation in response."""
    title: str | None = None
    link: str | None = None
    source: str | None = None
    score: float | None = None


class QueryOut(BaseModel):
    """Response from GraphRAG query."""
    answer: str
    sources: list[SourceOut] = []


@router.get("/ask")
async def ask(
    repo: KnowledgeRepoDep,
    settings: SettingsDep,
    q: str = "",
    request: Request = None,
) -> dict[str, str]:
    """Simple GraphRAG query (GET method for quick testing).
    
    Query parameter:
    - q: The question to ask
    
    Returns:
        - answer: Generated response from knowledge graph
    """
    check_rate_limit(request, settings)
    
    if not q.strip():
        raise HTTPException(status_code=400, detail="Missing query parameter 'q'")
    
    result = repo.query(q)
    return {"answer": result.text}


@router.post("/api/query", response_model=QueryOut)
async def api_query(
    body: QueryIn,
    repo: KnowledgeRepoDep,
    settings: SettingsDep,
    request: Request = None,
) -> QueryOut:
    """Full GraphRAG query with structured response.
    
    Returns answer with source citations and confidence scores
    when available (Neo4j backend).
    """
    check_rate_limit(request, settings)
    
    result = repo.query(body.message)
    
    return QueryOut(
        answer=result.text,
        sources=[SourceOut(**s) for s in result.sources],
    )
