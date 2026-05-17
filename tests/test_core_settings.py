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

    def test_settings_default_values(self):
        """Test default values are set correctly."""
        # Clear any existing env vars that might interfere
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            
            # Check default Ollama settings
            assert settings.ollama.host == "http://localhost:11434"
            assert settings.ollama.model == "llama3.1:8b"
            assert settings.ollama.timeout == 120
            
            # Check default agent settings
            assert settings.agent.use_react is True
            assert settings.agent.use_legacy_pipeline is False
            assert settings.agent.react_max_iter == 5
            assert settings.agent.react_parse_retries == 3
            
            # Check default Neo4j settings
            assert settings.neo4j.enabled is False
            
    def test_settings_from_env(self):
        """Test loading settings from environment variables."""
        env_vars = {
            "OLLAMA_HOST": "http://ollama:11434",
            "OLLAMA_MODEL": "llama3.3:70b",
            "OLLAMA_TIMEOUT": "60",
            "AGENT_USE_REACT": "false",
            "AGENT_REACT_MAX_ITER": "10",
            "NEO4J_ENABLED": "true",
            "NEO4J_URI": "bolt://neo4j:7687",
            "NEO4J_USER": "testuser",
            "NEO4J_PASSWORD": "testpass",
        }
        
        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            
            assert settings.ollama.host == "http://ollama:11434"
            assert settings.ollama.model == "llama3.3:70b"
            assert settings.ollama.timeout == 60
            assert settings.agent.use_react is False
            assert settings.agent.react_max_iter == 10
            assert settings.neo4j.enabled is True
            assert settings.neo4j.uri == "bolt://neo4j:7687"
            assert settings.neo4j.user == "testuser"
            assert settings.neo4j.password == "testpass"

    def test_cors_origins_parsing(self):
        """Test CORS origins are parsed correctly."""
        # Test with string
        with patch.dict(os.environ, {"CORS_ORIGINS": "*"}, clear=True):
            settings = Settings()
            assert settings.cors.get_origins_list() == ["*"]
        
        # Test with comma-separated list
        with patch.dict(
            os.environ, 
            {"CORS_ORIGINS": "http://localhost:3000,http://localhost:8080"}, 
            clear=True
        ):
            settings = Settings()
            assert settings.cors.get_origins_list() == [
                "http://localhost:3000", 
                "http://localhost:8080"
            ]

    def test_settings_singleton(self):
        """Test get_settings() returns cached instance."""
        # Reset singleton
        import core.settings
        core.settings._settings = None
        
        # First call should create new instance
        settings1 = get_settings()
        
        # Second call should return same instance
        settings2 = get_settings()
        
        assert settings1 is settings2
        
    def test_web_ui_dir_path(self):
        """Test web_ui_dir is a valid Path."""
        settings = Settings()
        assert isinstance(settings.web_ui_dir, Path)
        
    def test_rate_limit_settings(self):
        """Test rate limiting configuration."""
        with patch.dict(
            os.environ,
            {"RATE_LIMIT_MAX_PER_WINDOW": "100", "RATE_LIMIT_WINDOW_SEC": "60"},
            clear=True
        ):
            settings = Settings()
            assert settings.rate_limit.max_per_window == 100
            assert settings.rate_limit.window_sec == 60
