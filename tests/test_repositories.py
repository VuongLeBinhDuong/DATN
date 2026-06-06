"""Tests for repositories/ - Data access layer.

Tests Repository pattern implementations: KnowledgeRepository interface,
Neo4jRepository, and GraphRAGCLIRepository.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from repositories.base import QueryResult
from repositories.factory import get_default_repository, get_knowledge_repository
from repositories.neo4j_repo import Neo4jRepository


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
        """Test initialization load config by default."""
        with patch("repositories.neo4j_repo.load_neo4j_config") as mock_load:
            mock_load.return_value = {"uri": "bolt://localhost:7687", "user": "neo4j"}
            repo = Neo4jRepository()
            assert repo.config == {"uri": "bolt://localhost:7687", "user": "neo4j"}
            assert repo._driver is None

    def test_get_connection_params(self):
        """Test connection params extraction (prioritizing env variables)."""
        # 1. Fallback to config
        repo = Neo4jRepository(config={"uri": "bolt://config-uri:7687", "user": "config-user", "password": "config-password"})
        with patch.dict(os.environ, {}, clear=True):
            params = repo._get_connection_params()
            assert params["uri"] == "bolt://config-uri:7687"
            assert params["user"] == "config-user"
            assert params["password"] == "config-password"

        # 2. Env variable priority
        repo = Neo4jRepository(config={"uri": "bolt://config-uri:7687", "user": "config-user", "password": "config-password"})
        env_vars = {
            "NEO4J_URI": "bolt://env-uri:7687",
            "NEO4J_USER": "env-user",
            "NEO4J_PASSWORD": "env-password",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            params = repo._get_connection_params()
            assert params["uri"] == "bolt://env-uri:7687"
            assert params["user"] == "env-user"
            assert params["password"] == "env-password"

    def test_is_ready_connected(self):
        """Test is_ready returns True if Neo4j driver verifies connectivity."""
        config = {"uri": "bolt://localhost:7687", "user": "neo4j", "password": "pwd", "enabled": True}
        repo = Neo4jRepository(config=config)
        
        mock_driver = MagicMock()
        mock_driver.verify_connectivity.return_value = True
        
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver) as mock_driver_factory:
            # mock neo4j enabled check
            with patch("repositories.neo4j_repo.neo4j_enabled", return_value=True):
                assert repo.is_ready() is True
                mock_driver_factory.assert_called_once_with("bolt://127.0.0.1:7687", auth=("neo4j", "pwd"))

    def test_is_ready_not_connected(self):
        """Test is_ready returns False if driver verification throws exception."""
        config = {"uri": "bolt://localhost:7687", "user": "neo4j", "password": "pwd", "enabled": True}
        repo = Neo4jRepository(config=config)
        
        with patch("neo4j.GraphDatabase.driver", side_effect=Exception("Connection failed")):
            with patch("repositories.neo4j_repo.neo4j_enabled", return_value=True):
                assert repo.is_ready() is False

    def test_health_check_success(self):
        """Test health check returns success when populated with nodes."""
        config = {"uri": "bolt://localhost:7687", "user": "neo4j", "password": "pwd", "database": "neo4j", "enabled": True}
        repo = Neo4jRepository(config=config)
        
        mock_session = MagicMock()
        mock_session.run.return_value.single.return_value = {"l": "GraphEntity"}
        
        mock_driver = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session
        
        with patch("neo4j.GraphDatabase.driver", return_value=mock_driver):
            with patch("repositories.neo4j_repo.neo4j_enabled", return_value=True):
                health = repo.health_check()
                assert health["ok"] is True
                assert health["graph_populated"] is True

    def test_query_caching_and_execution(self):
        """Test repository querying logic, cache integration and retrieval pipeline invocation."""
        config = {"uri": "bolt://localhost:7687", "user": "neo4j", "password": "pwd", "enabled": True}
        repo = Neo4jRepository(config=config)
        
        # Mock retrieval pipeline response
        mock_context = "Extracted Neo4j context"
        mock_hits = [{"title": "Hit1", "score": 0.8}]
        
        # Reset simple cache
        from core.cache import clear_query_cache
        clear_query_cache()
        
        with patch("llm_pipeline.graphrag_query.run_graphrag_query_with_sources", return_value=(mock_context, mock_hits)):
            # 1. Cold query (Cache miss, triggers retrieve)
            res1 = repo.query("Flu query", use_cache=True)
            assert res1.text == "Extracted Neo4j context"
            assert res1.sources == [{"title": "Hit1", "score": 0.8}]
            assert res1.metadata["cached"] is False
            
            # 2. Warm query (Cache hit, does not call retrieve)
            with patch("llm_pipeline.graphrag_query.run_graphrag_query_with_sources") as mock_retrieve:
                res2 = repo.query("Flu query", use_cache=True)
                assert res2.text == "Extracted Neo4j context"
                assert res2.metadata["cached"] is True
                mock_retrieve.assert_not_called()

    def test_close(self):
        """Test close closes active driver."""
        repo = Neo4jRepository()
        mock_driver = MagicMock()
        repo._driver = mock_driver
        
        repo.close()
        mock_driver.close.assert_called_once()
        assert repo._driver is None


class TestGraphRAGCLIRepository:
    """Test cases for GraphRAGCLIRepository."""

    def test_init_resolves_data_dir(self, temp_graphrag_project):
        """Test that initialization successfully resolves output data dir."""
        from repositories.graphrag_cli_repo import GraphRAGCLIRepository
        
        with patch("repositories.graphrag_cli_repo._repo_root", return_value=temp_graphrag_project.parent):
            repo = GraphRAGCLIRepository()
            assert repo.root.name == "graphrag"
            assert repo.data_dir is not None
            assert repo.data_dir.name == "output"
            assert repo.is_ready() is True

    def test_health_check_missing_directories(self, tmp_path):
        """Test health check handles missing dirs gracefully."""
        from repositories.graphrag_cli_repo import GraphRAGCLIRepository
        
        # Empty temp dir (no graphrag directory)
        with patch("repositories.graphrag_cli_repo._repo_root", return_value=tmp_path):
            repo = GraphRAGCLIRepository()
            assert repo.is_ready() is False
            health = repo.health_check()
            assert health["ok"] is False
            assert "Missing graphrag" in health["detail"]

    def test_query_executes_subprocess(self, temp_graphrag_project):
        """Test executing query runs pytest/python-based graphrag CLI command."""
        from repositories.graphrag_cli_repo import GraphRAGCLIRepository
        
        with patch("repositories.graphrag_cli_repo._repo_root", return_value=temp_graphrag_project.parent):
            repo = GraphRAGCLIRepository()
            
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = b"GraphRAG answer text"
            mock_proc.stderr = b""
            
            with patch("subprocess.run", return_value=mock_proc) as mock_run:
                res = repo.query("Flu query terms")
                assert res.text == "GraphRAG answer text"
                assert res.sources == []
                
                # Check subprocess command args
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                assert "graphrag" in args
                assert "query" in args
                assert "Flu query terms" in args

    def test_query_fallback_executable(self, temp_graphrag_project):
        """Test fallback query mechanism using 'graphrag' binary when python execution fails."""
        from repositories.graphrag_cli_repo import GraphRAGCLIRepository
        
        with patch("repositories.graphrag_cli_repo._repo_root", return_value=temp_graphrag_project.parent):
            repo = GraphRAGCLIRepository()
            
            # Python -m graphrag returns non-zero (fails)
            mock_proc_py = MagicMock()
            mock_proc_py.returncode = 1
            mock_proc_py.stdout = b""
            mock_proc_py.stderr = b"No module found"
            
            # Falling back to executable 'graphrag' succeeds
            mock_proc_exe = MagicMock()
            mock_proc_exe.returncode = 0
            mock_proc_exe.stdout = b"Answer from fallback binary"
            
            with patch("subprocess.run", side_effect=[mock_proc_py, mock_proc_exe]):
                with patch("shutil.which", return_value="/usr/bin/graphrag"):
                    res = repo.query("My query")
                    assert res.text == "Answer from fallback binary"


class TestRepositoryFactory:
    """Test cases for repository factory helpers."""

    def test_factory_returns_neo4j_when_available(self, clean_settings_cache):
        """Test factory returns Neo4jRepository when auto is selected and Neo4j is configured & ready."""
        # 1. Configured and ready
        mock_neo4j = MagicMock(spec=Neo4jRepository)
        mock_neo4j.is_ready.return_value = True
        
        with patch("repositories.factory.Neo4jRepository", return_value=mock_neo4j):
            with patch("repositories.factory.neo4j_enabled", return_value=True):
                repo = get_knowledge_repository("auto")
                assert repo is mock_neo4j
                mock_neo4j.is_ready.assert_called_once()

    def test_factory_returns_cli_fallback(self, clean_settings_cache):
        """Test factory falls back to CLI-based GraphRAG when Neo4j is not configured/ready."""
        mock_neo4j = MagicMock(spec=Neo4jRepository)
        mock_neo4j.is_ready.return_value = False
        
        mock_cli = MagicMock()
        
        # In factory.py, GraphRAGCLIRepository is imported inside the functions
        # Patch the local import
        with patch("repositories.factory.Neo4jRepository", return_value=mock_neo4j):
            with patch("repositories.factory.neo4j_enabled", return_value=True):
                with patch("repositories.graphrag_cli_repo.GraphRAGCLIRepository", return_value=mock_cli):
                    repo = get_knowledge_repository("auto")
                    assert repo is mock_cli
                    mock_neo4j.close.assert_called_once()

    def test_factory_explicit_neo4j(self, clean_settings_cache):
        """Test factory creates Neo4jRepository when 'neo4j' backend explicitly requested."""
        mock_neo4j = MagicMock(spec=Neo4jRepository)
        with patch("repositories.factory.Neo4jRepository", return_value=mock_neo4j):
            repo = get_knowledge_repository("neo4j")
            assert repo is mock_neo4j

    def test_factory_explicit_cli(self, clean_settings_cache):
        """Test factory creates GraphRAGCLIRepository when 'cli' explicitly requested."""
        mock_cli = MagicMock()
        with patch("repositories.graphrag_cli_repo.GraphRAGCLIRepository", return_value=mock_cli):
            repo = get_knowledge_repository("cli")
            assert repo is mock_cli

    def test_factory_invalid_backend_raises(self):
        """Test factory raises ValueError on unknown backend choice."""
        with pytest.raises(ValueError) as exc_info:
            get_knowledge_repository("milvus")
        assert "Unknown backend" in str(exc_info.value)
