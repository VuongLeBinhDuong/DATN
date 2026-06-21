"""Tests for api/routes/ - FastAPI route handlers.

Tests HTTP endpoints using FastAPI TestClient and dependency overrides.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_agent_service, get_knowledge_repo, get_settings_dep
from api.main import app
from core.llm_backends import LLMBackendError
from core.settings import get_settings


@pytest.fixture
def client():
    """Provide a TestClient for API testing, ensuring overrides are cleared after test."""
    app.dependency_overrides.clear()
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestHealthEndpoints:
    """Test cases for health check endpoints."""

    def test_root_redirects_to_ui(self, client):
        """Test root path returns redirect or API info."""
        response = client.get("/")
        assert response.status_code in [200, 307, 308]

    def test_health_endpoint(self, client):
        """Test /health returns ok status."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_ready_endpoint(self, client):
        """Test /health/ready returns readiness info."""
        with patch("api.routes.health.compute_readiness") as mock_ready:
            mock_ready.return_value = {
                "status": "ready",
                "checks": {"ollama": True, "neo4j": False}
            }
            response = client.get("/health/ready")
            assert response.status_code == 200
            assert response.json()["status"] == "ready"


class TestOllamaEndpoints:
    """Test cases for Ollama proxy endpoints."""

    def test_ollama_health_available(self, client):
        """Test /api/ollama/health when Ollama is available."""
        mock_backend = MagicMock()
        mock_backend.is_available.return_value = True
        mock_backend.list_models.return_value = ["llama3.1:8b", "phi4:latest"]
        
        with patch("api.routes.ollama.OllamaBackend", return_value=mock_backend):
            response = client.get("/api/ollama/health")
            assert response.status_code == 200
            data = response.json()
            assert data["model_available"] is True
            assert "llama3.1:8b" in data["models"]

    def test_ollama_health_unavailable(self, client):
        """Test /api/ollama/health when Ollama is down."""
        mock_backend = MagicMock()
        mock_backend.is_available.side_effect = LLMBackendError("Connection refused")
        
        with patch("api.routes.ollama.OllamaBackend", return_value=mock_backend):
            response = client.get("/api/ollama/health")
            assert response.status_code == 503

    def test_ollama_chat_success(self, client):
        """Test /api/ollama/chat with valid request."""
        mock_backend = MagicMock()
        mock_backend.chat.return_value = "Response from Ollama"
        
        with patch("api.routes.ollama.OllamaBackend", return_value=mock_backend):
            response = client.post(
                "/api/ollama/chat",
                json={"message": "Hello", "model": "llama3.1:8b", "temperature": 0.7}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["message"] == "Response from Ollama"
            assert data["model"] == "llama3.1:8b"


class TestGraphRAGEndpoints:
    """Test cases for GraphRAG query endpoints."""

    def test_ask_endpoint_success(self, client):
        """Test GET /ask with valid query."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = MagicMock(
            text="Flu symptoms include fever and cough.",
            sources=[]
        )
        
        app.dependency_overrides[get_knowledge_repo] = lambda: mock_repo
        
        response = client.get("/ask?q=What are flu symptoms?")
        assert response.status_code == 200
        assert "Flu symptoms" in response.json()["answer"]

    def test_ask_endpoint_missing_query(self, client):
        """Test GET /ask without query parameter."""
        response = client.get("/ask")
        assert response.status_code == 400

    def test_api_query_success(self, client):
        """Test POST /api/query with valid request."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = MagicMock(
            text="Flu symptoms: fever, cough.",
            sources=[{"title": "Medical Source", "score": 0.95}]
        )
        
        app.dependency_overrides[get_knowledge_repo] = lambda: mock_repo
        
        response = client.post(
            "/api/query",
            json={"message": "What are flu symptoms?"}
        )
        assert response.status_code == 200
        assert response.json()["answer"] == "Flu symptoms: fever, cough."


class TestAgentEndpoints:
    """Test cases for Agent query endpoints."""

    def test_agent_query_success(self, client):
        """Test POST /api/agent-query with valid request."""
        mock_service = MagicMock()
        mock_service.execute.return_value = {
            "answer": "Flu symptoms include fever.",
            "plan": {},
            "errors": [],
            "sources": [],
            "context_graphrag_preview": "",
            "context_graphrag_full": "",
            "context_graphrag_total_chars": 0,
            "drug_images": [],
            "medication_plan": [],
            "reminders": [],
        }
        
        app.dependency_overrides[get_agent_service] = lambda: mock_service
        
        response = client.post(
            "/api/agent-query",
            json={
                "message": "What are flu symptoms?",
                "strategy": "auto"
            }
        )
        
        assert response.status_code == 200
        assert response.json()["answer"] == "Flu symptoms include fever."

    def test_agent_stream_success(self, client):
        """Test POST /api/agent-query/stream with valid request."""
        mock_service = MagicMock()
        
        def mock_stream():
            yield {"event": "step", "iteration": 1}
            yield {"event": "done", "answer": "Answer"}
            
        mock_service.execute_stream.return_value = mock_stream()
        
        app.dependency_overrides[get_agent_service] = lambda: mock_service
        
        response = client.post(
            "/api/agent-query/stream",
            json={
                "message": "What are flu symptoms?"
            }
        )
        
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/x-ndjson"

    def test_api_langchain_graph_query(self, client):
        """Test /api/langchain-graph-query endpoints."""
        mock_sources = [{"title": "Source 1", "score": 0.9}]
        
        with patch("services.retrieval_service.RetrievalService.query_langchain_graph_with_sources", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = ("Direct Answer", mock_sources)
            
            with patch("llm_pipeline.langchain_graphrag.retrieve_langchain_graph_context") as mock_context:
                mock_context.return_value = ("Context content", [])
                
                response = client.post(
                    "/api/langchain-graph-query",
                    json={"message": "flu symptoms"}
                )
                assert response.status_code == 200
                data = response.json()
                assert data["answer"] == "Direct Answer"
                assert data["sources"] == [{"title": "Source 1", "link": None, "source": None, "score": 0.9}]


class TestRateLimiting:
    """Test cases for rate limiting functionality."""

    def test_rate_limit_not_exceeded(self, client):
        """Test requests within rate limit are allowed."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_rate_limit_store_isolation(self):
        """Test rate limiting uses IP-based isolation."""
        from api.dependencies import _rate_limit_store, check_rate_limit
        
        _rate_limit_store.clear()
        
        mock_request_1 = MagicMock()
        mock_request_1.headers.get.return_value = None
        mock_request_1.client.host = "192.168.1.1"
        
        mock_request_2 = MagicMock()
        mock_request_2.headers.get.return_value = None
        mock_request_2.client.host = "192.168.1.2"
        
        mock_settings = MagicMock()
        mock_settings.rate_limit.max_per_window = 10
        mock_settings.rate_limit.window_sec = 60
        
        check_rate_limit(mock_request_1, mock_settings)
        check_rate_limit(mock_request_2, mock_settings)
        
        assert "192.168.1.1" in _rate_limit_store
        assert "192.168.1.2" in _rate_limit_store
