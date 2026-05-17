"""LLM answer generation for retrieved grounded context."""

from __future__ import annotations

import os
from pathlib import Path

import requests

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _prompts_dir() -> Path:
    """Thư mục prompt dùng chung cho agent / RAG Ollama: mặc định ``<repo>/prompts``."""
    raw = (os.getenv("LLM_APP_PROMPTS_DIR") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return _repo_root() / "prompts"
DEFAULT_GROUNDED_RAG_PROMPT = "grounded_rag_prompt.txt"
DEFAULT_AGENT_MERGED_PROMPT = "agent_merged_context_prompt.txt"
DIRECT_LLM_PROMPT = "direct_llm_prompt.txt"
SOCIAL_TURN_PROMPT = "social_turn_prompt.txt"


def answer_extractively(question: str, results: list[dict]) -> str:
    """Trả lời bằng đoạn chunk xếp hạng đầu, không gọi LLM."""
    if not results:
        return "No sufficiently relevant passages were found in the knowledge base."
    best = results[0]
    return (
        f"Closest match to your question '{question}':\n"
        f"- {best.get('text', '')}\n\n"
        f"Top source:\n- {best.get('title', '')}\n- {best.get('link', '')}"
    )


def _read_prompt_file(basename: str) -> str:
    p = _prompts_dir() / basename
    if not p.is_file():
        raise FileNotFoundError(f"Missing prompt file: {p}")
    return p.read_text(encoding="utf-8")


def _rag_llm_user_message(question: str, context: str, *, prompt_basename: str) -> str:
    env_override = (os.getenv("RAG_GROUNDED_PROMPT_BASENAME") or "").strip()
    name = env_override or prompt_basename
    template = _read_prompt_file(name)
    return template.format(question=question, context_data=context)


def _direct_llm_user_message(question: str) -> str:
    q = (question or "").strip()
    try:
        template = _read_prompt_file(DIRECT_LLM_PROMPT)
        return template.format(question=q)
    except FileNotFoundError:
        return (
            "Bạn là trợ lý y tế. Trả lời ngắn gọn, an toàn, tiếng Việt.\n\n"
            f"Câu hỏi: {q}\n"
        )


def answer_with_ollama(
    question: str,
    context: str,
    model_name: str,
    ollama_host: str,
    timeout: int,
    *,
    grounded: bool = True,
    prompt_basename: str | None = None,
) -> str:
    if grounded:
        base = prompt_basename or DEFAULT_GROUNDED_RAG_PROMPT
        prompt = _rag_llm_user_message(question, context, prompt_basename=base)
        temp = 0.25
    else:
        if prompt_basename:
            template = _read_prompt_file(prompt_basename)
            prompt = template.format(question=(question or "").strip())
        else:
            prompt = _direct_llm_user_message(question)
        temp = 0.2
    url = ollama_host.rstrip("/") + "/api/chat"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": temp},
    }
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return data.get("message", {}).get("content", "").strip()
