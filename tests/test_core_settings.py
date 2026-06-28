"""Tests for core/settings.py - Centralized configuration.

Tests Pydantic settings validation, loading from environment,
and the singleton get_settings() function.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from core.settings import Settings, get_settings


class TestSettings:
    """Test cases for Settings class."""

    def test_settings_default_values(self, clean_settings_cache):
        """Test default values are set correctly based on Settings defaults."""
        # Clear any existing env vars that might interfere
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Check default Ollama settings
            assert settings.ollama.host == "http://localhost:11434"
            assert settings.ollama.model == "llama3.2:3b"
            assert settings.ollama.timeout == 120
            
            # Check default agent settings
            assert settings.agent.use_react is True
            assert settings.agent.use_legacy_pipeline is False
            assert settings.agent.react_max_iter == 3
            assert settings.agent.react_parse_retries == 2
            
            # Check default Neo4j settings
            assert settings.neo4j.enabled is False
            assert settings.neo4j.database == "neo4j"
            
            # Check default rate limiting
            assert settings.rate_limit.max_per_window == 30
            assert settings.rate_limit.window_sec == 60

    def test_settings_from_env(self, clean_settings_cache):
        """Test loading settings from environment variables."""
        env_vars = {
            "OLLAMA_HOST": "https://ollama.mycloud.com",
            "OLLAMA_MODEL": "llama3.3:70b",
            "OLLAMA_TIMEOUT": "60",
            "AGENT_USE_REACT": "false",
            "AGENT_REACT_MAX_ITER": "8",
            "NEO4J_ENABLED": "true",
            "NEO4J_URI": "bolt://neo4j-host:7687",
            "NEO4J_USER": "testuser",
            "NEO4J_PASSWORD": "testpass",
            "NEO4J_DATABASE": "my-db",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            
            assert settings.ollama.host == "https://ollama.mycloud.com"
            assert settings.ollama.model == "llama3.3:70b"
            assert settings.ollama.timeout == 60
            assert settings.agent.use_react is False
            assert settings.agent.react_max_iter == 8
            assert settings.neo4j.enabled is True
            assert settings.neo4j.uri == "bolt://neo4j-host:7687"
            assert settings.neo4j.user == "testuser"
            assert settings.neo4j.password == "testpass"
            assert settings.neo4j.database == "my-db"

    def test_cors_origins_parsing(self, clean_settings_cache):
        """Test CORS origins are parsed correctly."""
        # Test with string '*'
        from core.settings import CorsSettings
        settings = Settings(cors=CorsSettings(origins="*"))
        assert settings.cors.get_origins_list() == ["*"]
        
        # Test with comma-separated list
        settings = Settings(cors=CorsSettings(origins="http://localhost:3000, http://localhost:8080, https://myapp.com"))
        assert settings.cors.get_origins_list() == [
            "http://localhost:3000", 
            "http://localhost:8080",
            "https://myapp.com"
        ]

    def test_settings_singleton(self, clean_settings_cache):
        """Test get_settings() returns cached instance."""
        # First call should create new instance
        settings1 = get_settings()
        
        # Second call should return same instance
        settings2 = get_settings()
        
        assert settings1 is settings2

    def test_web_ui_dir_path(self, clean_settings_cache):
        """Test web_ui_dir is a valid Path under the repo root."""
        settings = Settings()
        assert isinstance(settings.web_ui_dir, Path)
        assert settings.web_ui_dir.name == "web_ui"

    def test_rate_limit_settings(self, clean_settings_cache):
        """Test rate limiting configuration."""
        with patch.dict(
            os.environ,
            {"RATE_WINDOW_SEC": "120", "RATE_MAX_PER_WINDOW": "100"},
            clear=True
        ):
            settings = Settings()
            assert settings.rate_limit.window_sec == 120
            assert settings.rate_limit.max_per_window == 100

    def test_invalid_ollama_host_validation(self, clean_settings_cache):
        """Test validation fails for invalid Ollama host protocol."""
        from pydantic import ValidationError
        
        with patch.dict(os.environ, {"OLLAMA_HOST": "ftp://localhost"}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "must start with http:// or https://" in str(exc_info.value)

    def test_invalid_neo4j_uri_validation(self, clean_settings_cache):
        """Test validation fails for invalid Neo4j URI protocol."""
        from pydantic import ValidationError
        
        with patch.dict(os.environ, {"NEO4J_URI": "http://neo4j:7687"}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "must start with bolt://" in str(exc_info.value)
