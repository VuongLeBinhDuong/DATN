"""Tests for core/llm_backends.py - Ollama and OpenRouter clients.

Verifies correct request building, mocking outgoing HTTP payloads, streaming,
and fallback logic for custom LLM wrappers.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest
import requests

from core.llm_backends import (
    LLMBackendError,
    OllamaBackend,
    OpenRouterBackend,
    get_llm_backend,
    get_synthesis_backend,
)


class TestOllamaBackend:
    """Test cases for the Ollama integration backend."""

    def test_init_default_values(self, clean_settings_cache):
        """Test default host, model and timeout initialization."""
        backend = OllamaBackend()
        assert backend.host == "http://localhost:11434"
        assert backend.default_model == "llama3.2:3b"
        assert backend.timeout == 120

    def test_init_custom_values(self, clean_settings_cache):
        """Test custom configuration override options."""
        backend = OllamaBackend(
            host="http://ollama-prod:11434",
            timeout=30,
        )
        assert backend.host == "http://ollama-prod:11434"
        assert backend.timeout == 30

    def test_is_available_success(self):
        """Test backend is considered available when Ollama is running."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch("requests.Session.get", return_value=mock_response) as mock_get:
            backend = OllamaBackend()
            assert backend.is_available() is True
            mock_get.assert_called_once_with(
                "http://localhost:11434/api/tags",
                timeout=5,
            )

    def test_is_available_failure(self):
        """Test backend is unavailable when connection fails."""
        with patch("requests.Session.get", side_effect=requests.RequestException("Down")):
            backend = OllamaBackend()
            assert backend.is_available() is False

    def test_chat_success(self):
        """Test chat returns clean text response on HTTP 200."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Hello! I am a clinical assistant."}
        }
        
        with patch("requests.Session.post", return_value=mock_response) as mock_post:
            backend = OllamaBackend()
            messages = "Hello"
            
            res = backend.chat(messages, temperature=0.2)
            
            assert res == "Hello! I am a clinical assistant."
            mock_post.assert_called_once()
            
            # Verify request parameters
            kwargs = mock_post.call_args[1]
            assert kwargs["json"]["model"] == "llama3.2:3b"
            assert kwargs["json"]["options"]["temperature"] == 0.2
            assert kwargs["json"]["stream"] is False

    def test_chat_http_error(self):
        """Test chat raises LLMBackendError on bad HTTP status."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        # Make raise_for_status raise an HTTPError
        mock_response.raise_for_status.side_effect = requests.HTTPError(
            "500 Server Error",
            response=mock_response
        )
        
        with patch("requests.Session.post", return_value=mock_response):
            backend = OllamaBackend()
            with pytest.raises(LLMBackendError) as exc_info:
                backend.chat("hi")
            
            assert "Ollama HTTP error" in str(exc_info.value)
            assert exc_info.value.status_code == 500

    def test_chat_stream_yields_chunks(self):
        """Test streaming mode yields clean text chunks recursively."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.__enter__.return_value = mock_response
        
        # Stream response yields raw NDJSON lines
        chunks = [
            '{"message":{"content":"Hello"}}',
            '{"message":{"content":" beautiful"}}',
            '{"message":{"content":" world!"}}',
        ]
        mock_response.iter_lines.return_value = chunks
        
        with patch("requests.Session.post", return_value=mock_response):
            backend = OllamaBackend()
            messages = [{"role": "user", "content": "Say hello"}]
            
            result = list(backend.chat_stream(messages))
            
            assert result == ["Hello", " beautiful", " world!"]


class TestOpenRouterBackend:
    """Test cases for the OpenRouter API integration backend."""

    def test_init_without_api_key_raises(self, clean_settings_cache):
        """Test backend raises value error if API key is missing."""
        from core.settings import get_settings
        settings = get_settings()
        original_key = settings.openrouter.api_key
        settings.openrouter.api_key = ""
        try:
            with pytest.raises(LLMBackendError) as exc_info:
                OpenRouterBackend(api_key="")
            assert "OPENROUTER_API_KEY not configured" in str(exc_info.value)
        finally:
            settings.openrouter.api_key = original_key

    def test_init_with_api_key(self, clean_settings_cache):
        """Test backend initializes cleanly when API key is provided."""
        backend = OpenRouterBackend(api_key="sk-test-key")
        assert backend.api_key == "sk-test-key"
        assert backend.api_base == "https://openrouter.ai/api/v1"

    def test_chat_success(self, clean_settings_cache):
        """Test chat returns response message from OpenRouter structure."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter response"}}]
        }
        
        with patch("requests.Session.post", return_value=mock_response) as mock_post:
            backend = OpenRouterBackend(api_key="sk-key")
            res = backend.chat("Hi")
            
            assert res == "OpenRouter response"
            mock_post.assert_called_once()
            
            assert backend.session.headers["Authorization"] == "Bearer sk-key"

    def test_chat_stream_yields_chunks(self, clean_settings_cache):
        """Test streaming mode yields SSE chunks recursively."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.__enter__.return_value = mock_response
        
        # OpenRouter returns Server-Sent Events (SSE) format
        chunks = [
            'data: {"choices": [{"delta": {"content": "Hi"}}]}',
            'data: {"choices": [{"delta": {"content": " there"}}]}',
            'data: [DONE]',
        ]
        mock_response.iter_lines.return_value = chunks
        
        with patch("requests.Session.post", return_value=mock_response):
            backend = OpenRouterBackend(api_key="sk-key")
            result = list(backend.chat_stream([{"role": "user", "content": "Hi"}]))
            
            assert result == ["Hi", " there"]


class TestFactoryFunctions:
    """Test factory helper methods for retrieving backends based on settings."""

    def test_get_llm_backend_factory(self, clean_settings_cache):
        """Test auto-resolving backends from custom strategy overrides."""
        # Force ollama
        backend_ollama = get_llm_backend(backend="ollama")
        assert isinstance(backend_ollama, OllamaBackend)
        
        # Force openrouter
        backend_or = get_llm_backend(backend="openrouter", api_key="sk-key")
        assert isinstance(backend_or, OpenRouterBackend)

    def test_get_synthesis_backend_default(self, clean_settings_cache):
        """Test default fallback to Ollama if no explicit env variable set."""
        with patch.dict(os.environ, {}, clear=True):
            backend = get_synthesis_backend()
            assert backend == "ollama"

    def test_get_synthesis_backend_explicit_env(self, clean_settings_cache):
        """Test synthesis backend follows LLM_BACKEND env strategy."""
        # Set to openrouter
        env = {
            "LLM_BACKEND": "openrouter",
            "OPENROUTER_API_KEY": "sk-test",
        }
        with patch.dict(os.environ, env, clear=True):
            backend = get_synthesis_backend()
            assert backend == "openrouter"
