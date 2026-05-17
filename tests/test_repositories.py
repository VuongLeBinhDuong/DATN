"""Tests for repositories/ - Data access layer.

Tests Repository pattern implementations: KnowledgeRepository interface,
Neo4jRepository, and GraphRAGCLIRepository.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from repositories.base import KnowledgeRepository, QueryResult
from repositories.factory import get_knowledge_repository
from repositories.neo4j_repo import Neo4jRepository
from repositories.graphrag_cli_repo import GraphRAGCLIRepository


class TestQueryResult:
    """Test cases for QueryResult dataclass."""

    def test_query_result_creation(self):
        """Test creating QueryResult with all fields."""
        result = QueryResult(
            text="Test answer",
            sources=[{"title": "Source 1", "score": 0.9}],
            score=0.95,
            metadata={"query_time": 1.2}
        )
        
        assert result.text == "Test answer"
        assert len(result.sources) == 1
        assert result.score == 0.95
        assert result.metadata["query_time"] == 1.2

    def test_query_result_with_defaults(self):
        """Test creating QueryResult with default values."""
        result = QueryResult(text="Simple answer", sources=[])
        
        assert result.score is None
        assert result.metadata is None

    def test_query_result_bool_truthy(self):
        """Test QueryResult is truthy when text is non-empty."""
        result = QueryResult(text="Has content", sources=[])
        assert bool(result) is True

    def test_query_result_bool_falsy(self):
        """Test QueryResult is falsy when text is empty."""
        result = QueryResult(text="", sources=[])
        assert bool(result) is False

    def test_query_result_bool_whitespace_only(self):
        """Test QueryResult is falsy when text is only whitespace."""
        result = QueryResult(text="   ", sources=[])
        assert bool(result) is False


class TestNeo4jRepository:
    """Test cases for Neo4jRepository."""

    def test_init_default_values(self):
        """Test default initialization."""
        repo = Neo4jRepository()
        assert repo.uri == "bolt://localhost:7687"
        assert repo.user == "neo4j"
        assert repo.password == "password"
        assert repo.top_k == 10
        assert repo._driver is None

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        repo = Neo4jRepository(
            uri="bolt://neo4j:7687",
            user="admin",
            password="secret",
            top_k=5
        )
        assert repo.uri == "bolt://neo4j:7687"
        assert repo.user == "admin"
        assert repo.password == "secret"
        assert repo.top_k == 5

    def test_is_ready_with_driver(self):
        """Test is_ready returns True when driver exists and connected."""
        mock_driver = MagicMock()
        
        repo = Neo4jRepository()
        repo._driver = mock_driver
        
        assert repo.is_ready() is True

    def test_is_ready_without_driver(self):
        """Test is_ready returns False when no driver."""
        repo = Neo4jRepository()
        repo._driver = None
        
        assert repo.is_ready() is False

    def test_close_without_driver(self):
        """Test close doesn't fail when no driver."""
        repo = Neo4jRepository()
        repo._driver = None
        
        # Should not raise
        repo.close()

    def test_close_with_driver(self):
        """Test close closes the driver."""
        mock_driver = MagicMock()
        
        repo = Neo4jRepository()
        repo._driver = mock_driver
        
        repo.close()
        
        mock_driver.close.assert_called_once()

    def test_context_manager(self):
        """Test repository works as context manager."""
        mock_driver = MagicMock()
        
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            repo = Neo4jRepository()
            with repo as r:
                assert r is repo

    def test_query_with_empty_question(self):
        """Test query with empty question returns empty result."""
        repo = Neo4jRepository()
        
        result = repo.query("")
        
        assert result.text == ""
        assert result.sources == []


class TestGraphRAGCLIRepository:
    """Test cases for GraphRAGCLIRepository."""

    def test_init_default_values(self):
        """Test default initialization."""
        repo = GraphRAGCLIRepository()
        assert repo.root_dir.name == "graphrag"
        assert repo.timeout == 60

    def test_init_custom_values(self):
        """Test initialization with custom root directory."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = GraphRAGCLIRepository(root_dir=tmpdir, timeout=120)
            assert str(repo.root_dir) == tmpdir
            assert repo.timeout == 120

    def test_is_ready_without_project(self):
        """Test is_ready returns False when no GraphRAG project."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = GraphRAGCLIRepository(root_dir=tmpdir)
            assert repo.is_ready() is False

    def test_is_ready_with_project(self):
        """Test is_ready returns True when GraphRAG project exists."""
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create output directory to simulate GraphRAG project
            output_dir = Path(tmpdir) / "output"
            output_dir.mkdir()
            
            repo = GraphRAGCLIRepository(root_dir=tmpdir)
            assert repo.is_ready() is True

    def test_health_check_without_project(self):
        """Test health_check returns not ready status."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = GraphRAGCLIRepository(root_dir=tmpdir)
            health = repo.health_check()
            
            assert health["ready"] is False
            assert health["error"] is not None


class TestRepositoryFactory:
    """Test cases for get_knowledge_repository factory function."""

    def test_factory_returns_neo4j_when_available(self):
        """Test factory returns Neo4jRepository when Neo4j is ready."""
        mock_neo4j = MagicMock(spec=Neo4jRepository)
        mock_neo4j.is_ready.return_value = True
        
        with patch("repositories.factory.Neo4jRepository", return_value=mock_neo4j):
            with patch("repositories.factory.GraphRAGCLIRepository") as mock_cli:
                repo = get_knowledge_repository("auto")
                
                assert isinstance(repo, MagicMock)
                mock_neo4j.is_ready.assert_called_once()

    def test_factory_returns_cli_when_neo4j_unavailable(self):
        """Test factory returns CLI when Neo4j is not ready."""
        mock_neo4j = MagicMock(spec=Neo4jRepository)
        mock_neo4j.is_ready.return_value = False
        
        mock_cli = MagicMock(spec=GraphRAGCLIRepository)
        
        with patch("repositories.factory.Neo4jRepository", return_value=mock_neo4j):
            with patch("repositories.factory.GraphRAGCLIRepository", return_value=mock_cli):
                repo = get_knowledge_repository("auto")
                
                assert repo is mock_cli

    def test_factory_explicit_neo4j(self):
        """Test factory with explicit 'neo4j' backend."""
        mock_neo4j = MagicMock(spec=Neo4jRepository)
        
        with patch("repositories.factory.Neo4jRepository", return_value=mock_neo4j):
            repo = get_knowledge_repository("neo4j")
            
            assert repo is mock_neo4j

    def test_factory_explicit_cli(self):
        """Test factory with explicit 'cli' backend."""
        mock_cli = MagicMock(spec=GraphRAGCLIRepository)
        
        with patch("repositories.factory.GraphRAGCLIRepository", return_value=mock_cli):
            repo = get_knowledge_repository("cli")
            
            assert repo is mock_cli

    def test_factory_invalid_backend_raises(self):
        """Test factory raises error for invalid backend."""
        with pytest.raises(ValueError) as exc_info:
            get_knowledge_repository("invalid")
        
        assert "Unknown backend" in str(exc_info.value)
