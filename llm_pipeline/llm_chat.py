"""Gọi LLM cho tổng hợp Neo4j: Ollama local hoặc OpenRouter (khi có API key)."""

from __future__ import annotations

import os
from typing import Literal

import requests


def synthesis_backend() -> Literal["openrouter", "ollama"]:
    """Ưu tiên Ollama, chỉ dùng OpenRouter khi explicitly set LLM_BACKEND=openrouter."""
    backend = os.getenv("LLM_BACKEND", "").lower()
    if backend == "openrouter":
        return "openrouter"
    return "ollama"


def chat_ollama(
    prompt: str,
    *,
    host: str,
    model: str,
    timeout: int,
    temperature: float,
    num_predict: int,
) -> str:
    url = host.rstrip("/") + "/api/chat"
    payload: dict = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
        },
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message") or {}).get("content", "").strip()


def chat_openrouter(
    prompt: str,
    *,
    model: str | None,
    timeout: int,
    temperature: float,
    max_tokens: int,
) -> str:
    api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    m = (model or os.getenv("OPENROUTER_MODEL") or "openai/gpt-4o-mini").strip()
    base = (os.getenv("OPENROUTER_API_BASE") or "https://openrouter.ai/api/v1").rstrip("/")
    url = base + "/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": (os.getenv("OR_SITE_URL") or "https://localhost").strip(),
        "X-Title": (os.getenv("OR_APP_NAME") or "llm_pipeline").strip(),
    }
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    return str(msg.get("content") or "").strip()
