"""Tests for api/routes/ - FastAPI route handlers.

Tests HTTP endpoints using FastAPI TestClient.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from core.llm_backends import LLMBackendError


@pytest.fixture
def client():
    """Provide a TestClient for API testing."""
    return TestClient(app)


class TestHealthEndpoints:
    """Test cases for health check endpoints."""

    def test_root_redirects_to_ui(self, client):
        """Test root path returns API info or redirects."""
        response = client.get("/")
        # Should either redirect or return API info
        assert response.status_code in [200, 307, 308]

    def test_health_endpoint(self, client):
        """Test /health returns ok status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_health_ready_endpoint(self, client):
        """Test /health/ready returns detailed readiness info."""
        with patch("api.routes.health.legacy_readiness") as mock_ready:
            mock_ready.return_value = {
                "status": "ready",
                "checks": {"ollama": True, "neo4j": False}
            }
            
            response = client.get("/health/ready")
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ready"


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

    def test_ollama_chat_validation_error(self, client):
        """Test /api/ollama/chat with invalid request."""
        response = client.post(
            "/api/ollama/chat",
            json={"message": "", "model": "llama3.1:8b"}  # Empty message
        )
        
        assert response.status_code == 422  # Validation error


class TestGraphRAGEndpoints:
    """Test cases for GraphRAG query endpoints."""

    def test_ask_endpoint_success(self, client):
        """Test GET /ask with valid query."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = MagicMock(
            text="Flu symptoms include fever and cough.",
            sources=[]
        )
        
        with patch("api.routes.graphrag.KnowledgeRepoDep", mock_repo):
            response = client.get("/ask?q=What are flu symptoms?")
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data

    def test_ask_endpoint_missing_query(self, client):
        """Test GET /ask without query parameter."""
        response = client.get("/ask")
        
        assert response.status_code == 400

    def test_api_query_success(self, client):
        """Test POST /api/query with valid request."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = MagicMock(
            text="Flu symptoms: fever, cough.",
            sources=[
                {"title": "Medical Source", "score": 0.95}
            ]
        )
        
        with patch("api.dependencies.get_knowledge_repo", return_value=mock_repo):
            response = client.post(
                "/api/query",
                json={"message": "What are flu symptoms?"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data
            assert "sources" in data


class TestAgentEndpoints:
    """Test cases for Agent query endpoints."""

    def test_agent_query_success(self, client):
        """Test POST /api/agent-query with valid request."""
        mock_service = MagicMock()
        mock_service.execute.return_value = {
            "answer": "Flu symptoms include fever.",
            "plan": [],
            "errors": [],
            "context": None,
            "context_graphrag_full": "",
            "context_graphrag_total_chars": 0,
            "drug_images": [],
            "medication_plan": [],
            "reminders": [],
        }
        
        with patch("api.routes.agent.AgentServiceDep", mock_service):
            response = client.post(
                "/api/agent-query",
                json={
                    "message": "What are flu symptoms?",
                    "use_react": True,
                    "strategy": "auto"
                }
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "answer" in data

    def test_agent_query_validation_error(self, client):
        """Test POST /api/agent-query with invalid request."""
        response = client.post(
            "/api/agent-query",
            json={"message": "", "use_react": True}  # Empty message
        )
        
        assert response.status_code == 422

    def test_agent_stream_success(self, client):
        """Test POST /api/agent-query/stream with valid request."""
        mock_service = MagicMock()
        
        def mock_stream():
            yield {"event": "step", "iteration": 1}
            yield {"event": "done", "answer": "Answer"}
        
        mock_service.execute_stream.return_value = mock_stream()
        
        with patch("api.routes.agent.AgentServiceDep", mock_service):
            response = client.post(
                "/api/agent-query/stream",
                json={
                    "message": "What are flu symptoms?",
                    "use_react": True,
                    "use_legacy_pipeline": False
                }
            )
            
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/x-ndjson"

    def test_agent_stream_legacy_not_supported(self, client):
        """Test streaming with legacy pipeline returns error."""
        response = client.post(
            "/api/agent-query/stream",
            json={
                "message": "Test",
                "use_legacy_pipeline": True,
                "use_react": False
            }
        )
        
        assert response.status_code == 400
        assert "streaming" in response.json()["detail"].lower()


class TestRateLimiting:
    """Test cases for rate limiting functionality."""

    def test_rate_limit_not_exceeded(self, client):
        """Test requests within rate limit are allowed."""
        # Make a few requests
        for _ in range(3):
            response = client.get("/health")
            assert response.status_code == 200

    def test_rate_limit_store_isolation(self):
        """Test rate limiting uses IP-based isolation."""
        from api.dependencies import _rate_limit_store, check_rate_limit
        
        # Clear store
        _rate_limit_store.clear()
        
        # Create mock requests with different IPs
        mock_request_1 = MagicMock()
        mock_request_1.headers.get.return_value = None
        mock_request_1.client.host = "192.168.1.1"
        
        mock_request_2 = MagicMock()
        mock_request_2.headers.get.return_value = None
        mock_request_2.client.host = "192.168.1.2"
        
        mock_settings = MagicMock()
        mock_settings.rate_limit.max_per_window = 10
        mock_settings.rate_limit.window_sec = 60
        
        # Both should pass
        check_rate_limit(mock_request_1, mock_settings)
        check_rate_limit(mock_request_2, mock_settings)
        
        # Store should have entries for both IPs
        assert "192.168.1.1" in _rate_limit_store
        assert "192.168.1.2" in _rate_limit_store
