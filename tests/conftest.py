"""Shared fixtures and configuration for tests.

This file is automatically loaded by pytest and makes fixtures
available to all test files.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from core.llm_backends import OllamaBackend, OpenRouterBackend
from repositories.base import QueryResult


@pytest.fixture(autouse=True)
def block_external_requests():
    """Ensure no real HTTP requests are made during tests."""
    with patch("requests.get") as mock_get, patch("requests.post") as mock_post:
        # Mock responses to avoid NoneType errors if code calls them without custom mocks
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {})
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {})
        yield mock_get, mock_post


@pytest.fixture
def clean_settings_cache():
    """Clear settings singleton cache before and after test."""
    from core.settings import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_ollama_backend() -> MagicMock:
    """Provide a mock OllamaBackend for testing."""
    backend = MagicMock(spec=OllamaBackend)
    backend.host = "http://localhost:11434"
    backend.default_model = "llama3.1:8b"
    backend.timeout = 120
    backend.is_available.return_value = True
    backend.chat.return_value = "Mock response from Ollama"
    backend.list_models.return_value = ["llama3.1:8b", "phi4:latest"]
    backend.chat_stream.return_value = iter(["Mock", " response", " stream"])
    return backend


@pytest.fixture
def mock_openrouter_backend() -> MagicMock:
    """Provide a mock OpenRouterBackend for testing."""
    backend = MagicMock(spec=OpenRouterBackend)
    backend.api_key = "mock-api-key"
    backend.api_base = "https://openrouter.ai/api/v1"
    backend.default_model = "openai/gpt-3.5-turbo"
    backend.timeout = 120
    backend.is_available.return_value = True
    backend.chat.return_value = "Mock response from OpenRouter"
    backend.chat_stream.return_value = iter(["Mock", " OpenRouter", " stream"])
    return backend


@pytest.fixture
def mock_query_result() -> QueryResult:
    """Provide a standard QueryResult for testing."""
    return QueryResult(
        text="This is a mock answer from the knowledge repository.",
        sources=[
            {"title": "Medical Source 1", "score": 0.95, "url": "http://example.com/1"},
            {"title": "Medical Source 2", "score": 0.87, "url": "http://example.com/2"},
        ],
        score=0.91,
        metadata={"backend": "mock", "cached": False, "query_time_ms": 150}
    )


@pytest.fixture
def mock_repository(mock_query_result) -> MagicMock:
    """Provide a mock KnowledgeRepository for testing."""
    repo = MagicMock()
    repo.query.return_value = mock_query_result
    repo.is_ready.return_value = True
    repo.health_check.return_value = {"ok": True, "ready": True, "detail": "OK"}
    return repo


@pytest.fixture
def mock_streaming_chunks() -> list[str]:
    """Provide mock streaming chunks for LLM chat_stream testing."""
    return [
        "Thought: I need to search for this information.\n",
        "Action: graphrag_query\n",
        "Action Input: query terms",
    ]


@pytest.fixture
def temp_graphrag_project(tmp_path) -> Path:
    """Create a temporary GraphRAG project structure with dummy data."""
    output_dir = tmp_path / "graphrag" / "output"
    output_dir.mkdir(parents=True)
    
    # Create required entities.parquet file to satisfy _resolve_graphrag_data_dir
    entities_file = output_dir / "entities.parquet"
    entities_file.touch()
    
    return tmp_path / "graphrag"


@pytest.fixture
def sample_react_output() -> dict[str, str]:
    """Provide sample ReAct outputs for parser testing."""
    return {
        "final_answer": (
            "Thought: The user is asking about flu symptoms.\n"
            "Final Answer: Các triệu chứng cảm cúm bao gồm: sốt, ho, đau họng, nghẹt mũi, mệt mỏi."
        ),
        "action": (
            "Thought: I need to search for flu symptoms.\n"
            "Action: graphrag_query\n"
            "Action Input: triệu chứng cảm cúm"
        ),
        "with_markdown": (
            "Thought: Let me search.\n"
            "```\n"
            "Action: graphrag_query\n"
            "Action Input: search terms\n"
            "```"
        ),
        "invalid": "This is just random text without proper format",
    }


# Configure pytest markers
def pytest_configure(config):
    """Configure custom pytest markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "requires_neo4j: marks tests requiring Neo4j connection"
    )
    config.addinivalue_line(
        "markers", "requires_ollama: marks tests requiring Ollama server"
    )
