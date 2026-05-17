"""Shared fixtures and configuration for tests.

This file is automatically loaded by pytest and makes fixtures
available to all test files.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

from core.llm_backends import OllamaBackend
from repositories.base import QueryResult


@pytest.fixture
def mock_ollama_backend():
    """Provide a mock OllamaBackend for testing."""
    backend = MagicMock(spec=OllamaBackend)
    backend.host = "http://localhost:11434"
    backend.timeout = 120
    backend.is_available.return_value = True
    backend.chat.return_value = "Mock response"
    return backend


@pytest.fixture
def mock_query_result():
    """Provide a standard QueryResult for testing."""
    return QueryResult(
        text="This is a mock answer from the knowledge repository.",
        sources=[
            {"title": "Medical Source 1", "score": 0.95, "url": "http://example.com/1"},
            {"title": "Medical Source 2", "score": 0.87, "url": "http://example.com/2"},
        ],
        score=0.91,
        metadata={"query_time_ms": 150}
    )


@pytest.fixture
def mock_repository(mock_query_result):
    """Provide a mock KnowledgeRepository for testing."""
    repo = MagicMock()
    repo.query.return_value = mock_query_result
    repo.is_ready.return_value = True
    repo.health_check.return_value = {"ready": True, "error": None}
    return repo


@pytest.fixture
def mock_streaming_chunks():
    """Provide mock streaming chunks for LLM chat_stream testing."""
    return [
        "Thought: I need to search for this information.\n",
        "Action: graphrag_query\n",
        "Action Input: query terms",
    ]


@pytest.fixture
def clean_settings_cache():
    """Clear settings singleton cache before test."""
    import core.settings
    original_settings = core.settings._settings
    core.settings._settings = None
    yield
    # Restore after test
    core.settings._settings = original_settings


@pytest.fixture
def temp_graphrag_project(tmp_path):
    """Create a temporary GraphRAG project structure."""
    output_dir = tmp_path / "graphrag" / "output"
    output_dir.mkdir(parents=True)
    
    # Create some mock parquet files
    (output_dir / "create_final_communities.parquet").touch()
    (output_dir / "create_final_text_units.parquet").touch()
    
    return tmp_path / "graphrag"


@pytest.fixture
def sample_react_output():
    """Provide sample ReAct outputs for parser testing."""
    return {
        "final_answer": """Thought: The user is asking about flu symptoms.
Final Answer: Common flu symptoms include fever, cough, sore throat, runny nose, and fatigue.""",
        
        "action": """Thought: I need to search for this information in the medical knowledge base.
Action: graphrag_query
Action Input: influenza symptoms treatment""",
        
        "with_markdown": """Thought: Let me search.
```
Action: graphrag_query
Action Input: search terms
```""",
        
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
