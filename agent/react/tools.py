"""Tool execution for ReAct agent.

Provides unified interface for:
- graphrag_query: Knowledge graph retrieval (via Repository pattern)
- pill_image_lookup: Drug image search
"""

from __future__ import annotations

from typing import Any

from agent.tools import (
    expand_query_with_llm,
    merge_retrieval_hits,
    pill_image_lookup_with_urls,
    try_auto_pill_images_for_question,
)
from repositories import get_knowledge_repository

# Repository instance (lazy-loaded)
_repo = None


def _get_repo():
    """Get or create knowledge repository singleton."""
    global _repo
    if _repo is None:
        _repo = get_knowledge_repository("auto")
    return _repo


def set_repository(repo) -> None:
    """Override default repository (useful for testing)."""
    global _repo
    _repo = repo


def run_graphrag_tool(
    action_input: str | None,
    original_question: str,
    use_expansion: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    """Execute graphrag_query tool with merged query strategy.
    
    Uses Repository pattern to abstract Neo4j/CLI backend.
    Combines original question with action input for better retrieval.
    
    Args:
        action_input: The specific search terms from ReAct
        original_question: The full user question for context
        use_expansion: Enable query expansion for short queries
        
    Returns:
        Tuple of (observation_text, retrieval_hits)
    """
    oq = (original_question or "").strip()
    ai = (action_input or "").strip()
    
    repo = _get_repo()
    
    # Query Expansion: expand short queries for better retrieval
    if use_expansion and len(oq.split()) <= 10:
        variations = expand_query_with_llm(oq, num_variations=3)
        all_results = []
        for var in variations:
            result = repo.query(var)
            all_results.append((result.text, result.sources))
        # Merge and deduplicate
        seen_sources = set()
        merged_texts = []
        merged_hits = []
        for text, sources in all_results:
            for src in sources:
                src_key = (src.get("title", ""), src.get("source", ""))
                if src_key not in seen_sources:
                    seen_sources.add(src_key)
                    merged_hits.append(src)
            if text.strip():
                merged_texts.append(text)
        return "\n\n".join(merged_texts), merged_hits

    if not oq:
        result = repo.query(ai)
        return result.text, result.sources

    if not ai or ai.casefold() == oq.casefold():
        result = repo.query(oq)
        return result.text, result.sources

    # Check if one contains the other
    oql, ail = oq.casefold(), ai.casefold()
    if oql in ail or ail in oql:
        result = repo.query(oq)
        return result.text, result.sources

    # Merge both for better retrieval
    result = repo.query(oq, retrieval_query=f"{oq} {ai}".strip())
    return result.text, result.sources


def run_pill_image_tool(action_input: str | None) -> tuple[str, list[str]]:
    """Execute pill_image_lookup tool.
    
    Args:
        action_input: Drug name or keyword to search
        
    Returns:
        Tuple of (observation_text, image_urls)
    """
    return pill_image_lookup_with_urls(action_input or "")


def merge_pill_observation(
    question: str,
    base_observation: str,
    current_image_urls: list[str],
) -> tuple[str, list[str]]:
    """Merge auto-detected pill images into observation.
    
    Args:
        question: User question for drug name detection
        base_observation: Base text from graphrag
        current_image_urls: Currently accumulated image URLs
        
    Returns:
        Tuple of (merged_observation, updated_image_urls)
    """
    extra, new_urls = try_auto_pill_images_for_question(question)

    # Filter out already-seen URLs
    filtered_urls = [u for u in new_urls if u and u not in current_image_urls]

    if not filtered_urls:
        return base_observation, current_image_urls

    # Update accumulated URLs
    updated_urls = current_image_urls + filtered_urls

    if not (extra or "").strip():
        return base_observation, updated_urls

    merged = (
        base_observation
        + "\n\n--- Ảnh minh họa (dataset crawl, tham khảo) ---\n"
        + extra
    )
    return merged, updated_urls
