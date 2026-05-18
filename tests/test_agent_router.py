"""Tests for agent/router.py - Routing logic between social and knowledge retrieval.

Tests heuristics, LLM routing calls, error fallbacks, and strategy decisions.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from agent.router import (
    RetrievalPlan,
    is_meta_conversational_opener,
    is_obvious_pure_social,
    plan_retrieval,
)


class TestAgentRouterHeuristics:
    """Test cases for the regex-based routing heuristics."""

    def test_pure_social_greetings(self):
        """Test detection of simple social greetings and goodbyes."""
        assert is_obvious_pure_social("hello") is True
        assert is_obvious_pure_social("xin chào") is True
        assert is_obvious_pure_social("Xin chào") is True
        assert is_obvious_pure_social("bye") is True
        assert is_obvious_pure_social("cảm ơn bạn") is True
        assert is_obvious_pure_social("ok") is True
        
        # Long messages are not pure social greetings
        assert is_obvious_pure_social("hello, " + "a" * 160) is False
        # Messages with actual questions/keywords are not pure social
        assert is_obvious_pure_social("xin chào paracetamol uống sao") is False

    def test_meta_conversational_openers(self):
        """Test detection of meta conversational openings (asking to ask)."""
        assert is_meta_conversational_opener("tôi muốn hỏi chút được không") is True
        assert is_meta_conversational_opener("để em hỏi vài điều") is True
        assert is_meta_conversational_opener("được không?") is True
        
        # Openers that contain medical terms should NOT be marked as conversational opener
        # so they can route to GraphRAG search
        assert is_meta_conversational_opener("tôi muốn hỏi chút về bệnh tiểu đường") is False
        assert is_meta_conversational_opener("cho em hỏi paracetamol dùng thế nào") is False


class TestPlanRetrieval:
    """Test cases for plan_retrieval orchestrator."""

    def test_strategy_graph_always_returns_graphrag(self):
        """Test strategy='graph' always executes GraphRAG without calling LLM or heuristics."""
        plan = plan_retrieval("xin chào", strategy="graph")
        
        assert plan.use_graphrag is True
        assert plan.router_route == "graphrag"
        assert plan.next_pipeline == "rag_llm"
        assert "strategy=graph" in plan.reason

    def test_strategy_custom_always_returns_graphrag(self):
        """Test strategy other than 'auto' and 'graph' yields graphrag."""
        plan = plan_retrieval("xin chào", strategy="custom")
        assert plan.use_graphrag is True

    @pytest.mark.parametrize(
        "query,expected_route",
        [
            ("xin chào", "social"),
            ("tạm biệt", "social"),
            ("để tôi hỏi chút được không?", "social"),
        ]
    )
    def test_heuristics_override_social(self, query, expected_route):
        """Test heuristics route greetings and openers directly to social."""
        with patch.dict(os.environ, {"AGENT_ROUTER_HEURISTICS": "true"}):
            plan = plan_retrieval(query, strategy="auto")
            assert plan.use_graphrag is False
            assert plan.router_route == expected_route
            assert "heuristic" in plan.reason

    def test_heuristics_disabled_calls_llm(self):
        """Test heuristics disabled forces LLM call for all queries."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "social"}
        }
        
        with patch.dict(os.environ, {"AGENT_ROUTER_HEURISTICS": "false"}):
            with patch("requests.post", return_value=mock_response) as mock_post:
                plan = plan_retrieval("xin chào", strategy="auto")
                
                assert plan.use_graphrag is False
                assert plan.router_route == "social"
                mock_post.assert_called_once()

    def test_llm_route_success_plain_text(self):
        """Test parser handles single word line response from LLM."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "graphrag"}
        }
        
        with patch("requests.post", return_value=mock_response):
            plan = plan_retrieval("Tôi bị đau đầu dữ dội", strategy="auto")
            assert plan.use_graphrag is True
            assert plan.router_route == "graphrag"
            assert plan.next_pipeline == "rag_llm"

    def test_llm_route_success_with_json_fallback(self):
        """Test parser falls back to JSON parsing if LLM outputs old format."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": '{"route": "social", "reason": "greeting"}'}
        }
        
        with patch("requests.post", return_value=mock_response):
            plan = plan_retrieval("Tôi bị đau đầu dữ dội", strategy="auto")
            assert plan.use_graphrag is False
            assert plan.router_route == "social"

    def test_llm_route_failure_falls_back_to_graphrag(self):
        """Test that if Ollama router request fails, it falls back safely to GraphRAG."""
        with patch("requests.post", side_effect=Exception("Ollama down")):
            plan = plan_retrieval("Câu hỏi bất kỳ", strategy="auto")
            
            # Safe default fallback on error is to retrieve
            assert plan.use_graphrag is True
            assert plan.router_route == "graphrag"
            assert "llm-router lỗi" in plan.reason
