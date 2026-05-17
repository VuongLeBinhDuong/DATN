"""Retrieval Service - GraphRAG and vector search operations."""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from repositories.base import KnowledgeRepository

logger = logging.getLogger(__name__)


class RetrievalService:
    """Service for knowledge retrieval operations."""

    def __init__(self, repository: KnowledgeRepository | None = None) -> None:
        """Initialize with optional repository."""
        self._repository = repository

    async def query(self, question: str, k: int = 5) -> str:
        """Query knowledge base."""
        if self._repository is None:
            return "No knowledge repository configured."
        result = await self._repository.query(question, k)
        return result.response

    async def query_langchain_graph(self, question: str) -> str:
        """Query using LangChain GraphRAG (for disease/symptom/drug entity graph).
        
        This uses the Neo4j graph built by langchain_graphrag/medical_qa_graph.ipynb
        with schema: Disease, Symptom, Drug, Treatment, BodyPart, Test, RiskFactor, Cause.
        """
        # Import here to avoid circular dependencies
        from llm_pipeline.langchain_graphrag import run_langchain_graphrag_query
        
        try:
            return run_langchain_graphrag_query(question)
        except Exception as e:
            logger.error(f"LangChain GraphRAG query failed: {e}")
            return f"Error querying LangChain Graph: {e}"

    async def query_langchain_graph_with_sources(self, question: str) -> tuple[str, list[dict]]:
        """Query LangChain GraphRAG with source tracking.
        
        Returns:
            Tuple of (answer_text, sources_list)
        """
        from llm_pipeline.langchain_graphrag import run_langchain_graphrag_query_with_sources
        
        try:
            return run_langchain_graphrag_query_with_sources(question)
        except Exception as e:
            logger.error(f"LangChain GraphRAG query with sources failed: {e}")
            return f"Error: {e}", []
