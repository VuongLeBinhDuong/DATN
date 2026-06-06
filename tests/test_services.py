"""Tests for services/ - Business logic layer.

Tests AgentService (orchestrator strategy selector) and RetrievalService.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.llm_backends import LLMBackendError
from repositories.base import QueryResult
from services.agent_service import AgentService
from services.retrieval_service import RetrievalService


class TestAgentService:
    """Test cases for AgentService orchestrator."""

    def test_init_defaults(self, clean_settings_cache):
        """Test AgentService default setup."""
        mock_llm = MagicMock()
        with patch("services.agent_service.get_llm_backend", return_value=mock_llm):
            service = AgentService()
            assert service.llm is mock_llm
            assert service.settings is not None

    def test_is_available_checks_llm(self):
        """Test is_available checks backend reachable status."""
        mock_llm = MagicMock()
        mock_llm.is_available.return_value = True
        
        service = AgentService(llm_backend=mock_llm)
        assert service.is_available() is True
        
        # Test backend error returns False
        mock_llm.is_available.side_effect = LLMBackendError("Unavailable")
        assert service.is_available() is False

    def test_execute_react_strategy(self, clean_settings_cache):
        """Test execute defaults to ReAct agent."""
        mock_llm = MagicMock()
        service = AgentService(llm_backend=mock_llm)
        
        mock_react_result = {"answer": "ReAct answer", "iterations": 1}
        
        with patch("agent.react.ReActAgent.run_sync", return_value=mock_react_result) as mock_run:
            res = service.execute("Flu symptoms")
            assert res == mock_react_result
            mock_run.assert_called_once_with("Flu symptoms", history=None)

    def test_execute_intent_router_direct_db(self, clean_settings_cache):
        """Test execute routes to direct_db for physiological lookup."""
        mock_llm = MagicMock()
        service = AgentService(llm_backend=mock_llm)
        
        # Test direct_db matching query
        query = "glucose của tôi là 7.5 mmol/L"
        res = service.execute(query)
        
        assert "KẾT QUẢ ĐỐI CHIẾU CHỈ SỐ LÂM SÀNG TỰ ĐỘNG" in res["answer"]
        assert res["sources"][0]["source"] == "Bộ Y tế Việt Nam / WHO Guidelines"

    def test_execute_stream_react(self, clean_settings_cache):
        """Test streaming execution yields events via ReAct agent."""
        mock_llm = MagicMock()
        service = AgentService(llm_backend=mock_llm)
        
        events = [{"event": "step", "content": "1"}]
        
        with patch("agent.react.ReActAgent.run_stream", return_value=iter(events)):
            stream = list(service.execute_stream("Hello"))
            assert stream == events


class TestRetrievalService:
    """Test cases for RetrievalService."""

    def test_query_no_repository(self):
        """Test query with no repository configured."""
        service = RetrievalService(repository=None)
        
        # Since it is async, we run it synchronously in test using asyncio
        import asyncio
        res = asyncio.run(service.query("Query"))
        assert "No knowledge repository" in res

    def test_query_with_sync_repository(self):
        """Test query with a synchronous repository."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = QueryResult(text="Sync answer", sources=[])
        
        service = RetrievalService(repository=mock_repo)
        
        import asyncio
        res = asyncio.run(service.query("Query", k=10))
        assert res == "Sync answer"
        mock_repo.query.assert_called_once_with("Query", top_k=10)

    def test_query_with_async_repository(self):
        """Test query with an asynchronous repository."""
        mock_repo = MagicMock()
        # Mock query as an async function
        mock_repo.query = AsyncMock(return_value=QueryResult(text="Async answer", sources=[]))
        
        service = RetrievalService(repository=mock_repo)
        
        import asyncio
        res = asyncio.run(service.query("Query", k=3))
        assert res == "Async answer"
        mock_repo.query.assert_called_once_with("Query", top_k=3)

    def test_query_langchain_graph_success(self):
        """Test query_langchain_graph calls underlying module query."""
        service = RetrievalService()
        
        with patch("llm_pipeline.langchain_graphrag.run_langchain_graphrag_query", return_value="GraphRAG synthesis answer") as mock_query:
            import asyncio
            res = asyncio.run(service.query_langchain_graph("Flu causes"))
            assert res == "GraphRAG synthesis answer"
            mock_query.assert_called_once_with("Flu causes")

    def test_query_langchain_graph_exception(self):
        """Test query_langchain_graph handles exceptions gracefully."""
        service = RetrievalService()
        
        with patch("llm_pipeline.langchain_graphrag.run_langchain_graphrag_query", side_effect=Exception("Database down")):
            import asyncio
            res = asyncio.run(service.query_langchain_graph("Flu causes"))
            assert "Error querying LangChain Graph" in res

    def test_query_langchain_graph_with_sources(self):
        """Test query_langchain_graph_with_sources returns tuple of answer and sources list."""
        service = RetrievalService()
        mock_sources = [{"title": "Article 1", "score": 0.9}]
        
        with patch(
            "llm_pipeline.langchain_graphrag.run_langchain_graphrag_query_with_sources",
            return_value=("Answer with sources", mock_sources)
        ) as mock_query:
            import asyncio
            ans, src = asyncio.run(service.query_langchain_graph_with_sources("Flu"))
            assert ans == "Answer with sources"
            assert src == mock_sources
            mock_query.assert_called_once_with("Flu")


def test_prune_subgraph_clinical_noise_reduction():
    """Test prune_subgraph correctly removes isolated, generic, and noisy nodes."""
    from retrieval.graph_first import prune_subgraph
    
    # Mock subgraph with valid nodes, a generic node, a noisy punctuation node, and an isolated node
    mock_subgraph = {
        "entities": [
            {"entity_id": "ent_diabetes", "name": "Tiểu đường", "type": "Disease"},
            {"entity_id": "ent_metformin", "name": "Metformin", "type": "Drug"},
            {"entity_id": "ent_isolated", "name": "Isolated Node", "type": "Disease"},
            {"entity_id": "ent_noisy_punc", "name": "!!!", "type": "Disease"},
            {"entity_id": "ent_generic", "name": "Some Generic", "type": "Generic"},
        ],
        "edges": [
            {"source": "ent_diabetes", "target": "ent_metformin", "relation": "TREATS"}
        ]
    }
    
    # Run the soft pruning
    pruned = prune_subgraph(mock_subgraph, seed_ids=["ent_diabetes"])
    
    # Assertions
    entity_ids = {e["entity_id"] for e in pruned["entities"]}
    
    # Active/connected components should be kept
    assert "ent_diabetes" in entity_ids
    assert "ent_metformin" in entity_ids
    
    # Noisy, isolated, and generic components should be pruned
    assert "ent_isolated" not in entity_ids
    assert "ent_noisy_punc" not in entity_ids
    assert "ent_generic" not in entity_ids
    
    # Edges should remain intact
    assert len(pruned["edges"]) == 1
    assert pruned["edges"][0]["relation"] == "TREATS"
