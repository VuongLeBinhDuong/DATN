"""Abstract base classes and implementations for LLM backends.

Provides unified interface for Ollama and OpenRouter APIs.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import Any, Literal

import requests

from core.settings import get_settings

logger = logging.getLogger(__name__)


def get_synthesis_backend() -> Literal["ollama", "openrouter"]:
    """Determine which LLM backend to use for synthesis.
    
    Priority:
    1. LLM_BACKEND env var explicitly set -> use that
    2. Default -> ollama (ƯU TIÊN - chạy local)
    3. Chỉ dùng openrouter khi explicitly set LLM_BACKEND=openrouter
       hoặc Ollama không khả dụng và có OPENROUTER_API_KEY
    """
    # Explicit backend choice takes priority
    explicit = os.getenv("LLM_BACKEND", "").lower()
    if explicit == "openrouter":
        return "openrouter"
    if explicit == "ollama":
        return "ollama"
    
    # Mặc định: Ưu tiên Ollama local (không auto-switch sang OpenRouter)
    return "ollama"


class LLMBackend(ABC):
    """Abstract base class for LLM backends.
    
    All LLM implementations must inherit from this class
    and implement the chat method.
    """

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout
        self._session: requests.Session | None = None

    @property
    def session(self) -> requests.Session:
        """Lazy-loaded HTTP session with connection pooling."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self._get_default_headers())
        return self._session

    @abstractmethod
    def _get_default_headers(self) -> dict[str, str]:
        """Return default HTTP headers for this backend."""
        ...

    @abstractmethod
    def chat(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Send chat completion request.
        
        Args:
            prompt: The user prompt text
            model: Model identifier (backend-specific)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Backend-specific options
            
        Returns:
            Generated text response
            
        Raises:
            LLMBackendError: On API errors or timeouts
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if backend service is reachable."""
        ...

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream chat completion tokens.
        
        Args:
            messages: List of message dicts with role/content
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            stop: Stop sequences
            **kwargs: Backend-specific options
            
        Yields:
            Token strings as they are generated
        """
        ...

    def close(self) -> None:
        """Close HTTP session and release resources."""
        if self._session is not None:
            self._session.close()
            self._session = None

    def __enter__(self) -> LLMBackend:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class LLMBackendError(Exception):
    """Raised when LLM backend encounters an error."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class OllamaBackend(LLMBackend):
    """Ollama local LLM backend.
    
    Communicates with Ollama HTTP API at /api/chat endpoint.
    """

    def __init__(
        self,
        host: str | None = None,
        timeout: int = 120,
    ) -> None:
        super().__init__(timeout)
        settings = get_settings()
        self.host = (host or settings.ollama.host).rstrip("/")
        self.default_model = settings.ollama.model
        self.num_ctx = settings.ollama.num_ctx

    def _get_default_headers(self) -> dict[str, str]:
        return {"Content-Type": "application/json"}

    def is_available(self) -> bool:
        """Check if Ollama server is running."""
        try:
            resp = self.session.get(
                f"{self.host}/api/tags",
                timeout=5,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        """Get list of available models from Ollama."""
        try:
            resp = self.session.get(
                f"{self.host}/api/tags",
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            return [str(m.get("name", "")) for m in data.get("models", []) if m.get("name")]
        except requests.RequestException as e:
            raise LLMBackendError(f"Failed to list Ollama models: {e}")

    def chat(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        num_predict: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Send chat request to Ollama.
        
        Args:
            num_predict: Ollama-specific max tokens parameter
        """
        model_name = model or self.default_model
        url = f"{self.host}/api/chat"

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
            },
        }

        # Ollama uses num_predict instead of max_tokens
        tokens = num_predict or max_tokens
        if tokens is not None:
            payload["options"]["num_predict"] = max(256, min(tokens, 8192))

        # Add any extra options
        for key, value in kwargs.items():
            if value is not None:
                payload["options"][key] = value

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as e:
            detail = getattr(e.response, "text", str(e))[:2000]
            raise LLMBackendError(f"Ollama HTTP error: {detail}", e.response.status_code)
        except requests.RequestException as e:
            raise LLMBackendError(f"Ollama request failed: {e}")

        return (data.get("message") or {}).get("content", "").strip()

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream chat completion tokens from Ollama.
        
        Args:
            messages: List of message dicts with role/content
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            stop: Stop sequences
            **kwargs: Additional options
            
        Yields:
            Token strings as they are generated
        """
        import json as json_module

        model_name = model or self.default_model
        url = f"{self.host}/api/chat"

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_ctx": self.num_ctx,
            },
        }

        if max_tokens is not None:
            payload["options"]["num_predict"] = max(256, min(max_tokens, 8192))

        if stop:
            payload["options"]["stop"] = stop

        for key, value in kwargs.items():
            if value is not None:
                payload["options"][key] = value

        try:
            with self.session.post(url, json=payload, stream=True, timeout=self.timeout) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    try:
                        obj = json_module.loads(line)
                    except json_module.JSONDecodeError:
                        continue
                    if obj.get("done"):
                        break
                    content = (obj.get("message") or {}).get("content") or ""
                    if content:
                        yield content
        except requests.HTTPError as e:
            detail = getattr(e.response, "text", str(e))[:2000]
            raise LLMBackendError(f"Ollama HTTP error: {detail}", e.response.status_code)
        except requests.RequestException as e:
            raise LLMBackendError(f"Ollama request failed: {e}")


class OpenRouterBackend(LLMBackend):
    """OpenRouter API backend for cloud LLMs.
    
    OpenAI-compatible API for accessing various models.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        timeout: int = 120,
    ) -> None:
        super().__init__(timeout)
        settings = get_settings()

        self.api_key = api_key or settings.openrouter.api_key
        if not self.api_key:
            raise LLMBackendError("OPENROUTER_API_KEY not configured")

        self.api_base = (api_base or settings.openrouter.api_base).rstrip("/")
        self.default_model = settings.openrouter.model or "openai/gpt-3.5-turbo"

    def _get_default_headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "HTTP-Referer": "https://localhost",  # OpenRouter requires this
            "X-Title": "DATN Medical RAG System",
        }

    def is_available(self) -> bool:
        """Check if API key is valid by making a test request."""
        try:
            resp = self.session.get(
                "https://openrouter.ai/api/v1/auth/key",
                timeout=10,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def chat(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """Send chat request to OpenRouter."""
        model_name = model or self.default_model
        url = f"{self.api_base}/chat/completions"

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            resp = self.session.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
        except requests.HTTPError as e:
            detail = getattr(e.response, "text", str(e))[:2000]
            raise LLMBackendError(f"OpenRouter HTTP error: {detail}", e.response.status_code)
        except requests.RequestException as e:
            raise LLMBackendError(f"OpenRouter request failed: {e}")

        choices = data.get("choices", [])
        if not choices:
            raise LLMBackendError("OpenRouter returned empty choices")

        return (choices[0].get("message") or {}).get("content", "").strip()

    def chat_stream(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> Iterator[str]:
        """Stream chat completion tokens from OpenRouter (OpenAI-compatible).
        
        Args:
            messages: List of message dicts with role/content
            model: Model identifier
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            stop: Stop sequences
            **kwargs: Additional options
            
        Yields:
            Token strings as they are generated
        """
        import json as json_module

        model_name = model or self.default_model
        url = f"{self.api_base}/chat/completions"

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if stop:
            payload["stop"] = stop

        try:
            with self.session.post(url, json=payload, stream=True, timeout=self.timeout) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        line = line[6:]  # Remove "data: " prefix
                    if line == "[DONE]":
                        break
                    try:
                        obj = json_module.loads(line)
                    except json_module.JSONDecodeError:
                        continue
                    choices = obj.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        yield content
        except requests.HTTPError as e:
            detail = getattr(e.response, "text", str(e))[:2000]
            raise LLMBackendError(f"OpenRouter HTTP error: {detail}", e.response.status_code)
        except requests.RequestException as e:
            raise LLMBackendError(f"OpenRouter request failed: {e}")


def get_llm_backend(
    backend: Literal["auto", "ollama", "openrouter", "huggingface"] = "auto",
    **kwargs: Any,
) -> LLMBackend:
    """Factory function to get appropriate LLM backend.
    
    Args:
        backend: Which backend to use ('auto' picks based on config)
        **kwargs: Backend-specific initialization args
        
    Returns:
        Configured LLMBackend instance
        
    Raises:
        LLMBackendError: If requested backend is not available
    """
    if backend == "auto":
        backend = get_synthesis_backend()

    if backend == "openrouter":
        try:
            return OpenRouterBackend(**kwargs)
        except LLMBackendError:
            logger.warning("OpenRouter not configured, falling back to Ollama")
            return OllamaBackend(**kwargs)

    return OllamaBackend(**kwargs)
