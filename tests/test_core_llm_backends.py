"""Tests for core/llm_backends.py - LLM backend abstractions.

Tests OllamaBackend and OpenRouterBackend implementations.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from core.llm_backends import LLMBackendError, OllamaBackend, OpenRouterBackend


class TestOllamaBackend:
    """Test cases for OllamaBackend."""

    def test_init_default_values(self):
        """Test default initialization values."""
        backend = OllamaBackend()
        assert backend.host == "http://localhost:11434"
        assert backend.timeout == 120
        
    def test_init_custom_values(self):
        """Test initialization with custom values."""
        backend = OllamaBackend(host="http://ollama:11434", timeout=60)
        assert backend.host == "http://ollama:11434"
        assert backend.timeout == 60

    def test_is_available_success(self):
        """Test is_available returns True when Ollama responds."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"version": "0.1.0"}
        
        with patch("requests.get", return_value=mock_response):
            backend = OllamaBackend()
            assert backend.is_available() is True

    def test_is_available_failure(self):
        """Test is_available returns False when Ollama is down."""
        with patch("requests.get", side_effect=Exception("Connection refused")):
            backend = OllamaBackend()
            assert backend.is_available() is False

    def test_chat_success(self):
        """Test chat method with successful response."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Test response"}
        }
        
        with patch("requests.post", return_value=mock_response):
            backend = OllamaBackend()
            result = backend.chat("Hello", model="llama3.1:8b")
            assert result == "Test response"

    def test_chat_error_status_code(self):
        """Test chat raises LLMBackendError on error status."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch("requests.post", return_value=mock_response):
            backend = OllamaBackend()
            with pytest.raises(LLMBackendError) as exc_info:
                backend.chat("Hello")
            
            assert exc_info.value.status_code == 500
            assert "Internal Server Error" in str(exc_info.value)

    def test_chat_request_exception(self):
        """Test chat raises LLMBackendError on request failure."""
        with patch("requests.post", side_effect=Exception("Connection timeout")):
            backend = OllamaBackend()
            with pytest.raises(LLMBackendError) as exc_info:
                backend.chat("Hello")
            
            assert "Connection timeout" in str(exc_info.value)
            assert exc_info.value.status_code is None

    def test_list_models(self):
        """Test list_models returns model names."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [
                {"name": "llama3.1:8b"},
                {"name": "llama3.1:70b"},
                {"name": "phi4:latest"},
            ]
        }
        
        with patch("requests.get", return_value=mock_response):
            backend = OllamaBackend()
            models = backend.list_models()
            assert models == ["llama3.1:8b", "llama3.1:70b", "phi4:latest"]

    def test_chat_stream_yields_chunks(self):
        """Test chat_stream yields chunks from streaming response."""
        chunks = [
            b'{"message":{"content":"Hello"}}',
            b'{"message":{"content":" world"}}',
            b'{"message":{"content":"!"}}',
        ]
        
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = chunks
        mock_response.status_code = 200
        
        with patch("requests.post", return_value=mock_response):
            backend = OllamaBackend()
            messages = [{"role": "user", "content": "Say hello"}]
            
            result = list(backend.chat_stream(messages))
            
            assert result == ["Hello", " world", "!"]

    def test_chat_stream_handles_json_parse_error(self):
        """Test chat_stream handles invalid JSON gracefully."""
        chunks = [
            b'{"message":{"content":"Hello"}}',
            b'invalid json',
            b'{"message":{"content":"!"}}',
        ]
        
        mock_response = MagicMock()
        mock_response.iter_lines.return_value = chunks
        mock_response.status_code = 200
        
        with patch("requests.post", return_value=mock_response):
            backend = OllamaBackend()
            messages = [{"role": "user", "content": "Say hello"}]
            
            # Should not raise, just skip invalid chunks
            result = list(backend.chat_stream(messages))
            assert result == ["Hello", "!"]


class TestOpenRouterBackend:
    """Test cases for OpenRouterBackend."""

    def test_init_without_api_key(self):
        """Test initialization without API key works."""
        backend = OpenRouterBackend(api_key=None)
        assert backend.api_key is None
        assert backend.base_url == "https://openrouter.ai/api/v1"
        
    def test_init_with_api_key(self):
        """Test initialization with API key."""
        backend = OpenRouterBackend(
            api_key="test-key",
            base_url="https://custom.api.com"
        )
        assert backend.api_key == "test-key"
        assert backend.base_url == "https://custom.api.com"

    def test_is_available_without_key(self):
        """Test is_available returns False when no API key."""
        backend = OpenRouterBackend(api_key=None)
        assert backend.is_available() is False

    def test_chat_success(self):
        """Test chat with OpenRouter API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OpenRouter response"}}]
        }
        
        with patch("requests.post", return_value=mock_response):
            backend = OpenRouterBackend(api_key="test-key")
            result = backend.chat("Hello", model="anthropic/claude-3-opus")
            assert result == "OpenRouter response"

    def test_chat_without_api_key_raises(self):
        """Test chat raises error when no API key provided."""
        backend = OpenRouterBackend(api_key=None)
        
        with pytest.raises(LLMBackendError) as exc_info:
            backend.chat("Hello")
        
        assert "API key required" in str(exc_info.value)

    def test_list_models_success(self):
        """Test list_models returns available models."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "anthropic/claude-3-opus"},
                {"id": "openai/gpt-4"},
                {"id": "google/gemini-pro"},
            ]
        }
        
        with patch("requests.get", return_value=mock_response):
            backend = OpenRouterBackend(api_key="test-key")
            models = backend.list_models()
            
            assert len(models) == 3
            assert "anthropic/claude-3-opus" in models


class TestLLMBackendError:
    """Test cases for LLMBackendError exception."""

    def test_error_with_status_code(self):
        """Test error with status code."""
        error = LLMBackendError("Server error", status_code=503)
        assert str(error) == "Server error"
        assert error.status_code == 503

    def test_error_without_status_code(self):
        """Test error without status code."""
        error = LLMBackendError("Connection failed")
        assert str(error) == "Connection failed"
        assert error.status_code is None
