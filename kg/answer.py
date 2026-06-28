from __future__ import annotations

import os
from typing import Any

from kg.extract.json_utils import extract_first_json
from llm_pipeline.llm_chat import chat_ollama, chat_openrouter, synthesis_backend


ANSWER_PROMPT_TEMPLATE = """\
Bạn là trợ lý QA. Hãy trả lời câu hỏi dựa CHỈ trên các EVIDENCE chunks bên dưới.

Yêu cầu:
- Nếu không đủ thông tin trong evidence, hãy nói rõ không đủ dữ liệu.
- Trả về DUY NHẤT một JSON object với keys:
  - answer: string (tiếng Việt, rõ ràng)
  - citations: array of objects {{chunk_id: string, quote: string}}
- citations: trích các câu/đoạn ngắn (<= 300 ký tự) từ chunk tương ứng để chứng minh.

QUESTION:
{question}

EVIDENCE:
{evidence}
"""


def _format_evidence(chunks: list[dict[str, Any]], max_chars_each: int = 1800) -> str:
    blocks: list[str] = []
    for ch in chunks:
        cid = ch.get("chunk_id")
        text = (ch.get("text") or "").strip()
        if not cid or not text:
            continue
        blocks.append(f"[chunk_id={cid}]\n{text[:max_chars_each]}")
    return "\n\n".join(blocks) if blocks else "(none)"


def synthesize_answer_with_citations(question: str, evidence_chunks: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = ANSWER_PROMPT_TEMPLATE.format(question=question, evidence=_format_evidence(evidence_chunks))

    host = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL") or "llama3.2:3b"
    timeout = int(os.getenv("OLLAMA_TIMEOUT") or "120")
    temperature = float(os.getenv("KG_ANSWER_TEMPERATURE") or "0.2")
    num_predict = int(os.getenv("KG_ANSWER_NUM_PREDICT") or "2048")

    backend = synthesis_backend()
    if backend == "openrouter":
        or_model = os.getenv("OPENROUTER_MODEL") or None
        raw = chat_openrouter(prompt, model=or_model, timeout=timeout, temperature=temperature, max_tokens=min(num_predict, 4096))
    else:
        raw = chat_ollama(
            prompt,
            host=host,
            model=model,
            timeout=timeout,
            temperature=temperature,
            num_predict=num_predict,
        )

    data = extract_first_json(raw)
    if not isinstance(data, dict):
        return {"answer": str(raw).strip(), "citations": []}
    ans = str(data.get("answer") or "").strip()
    cits = data.get("citations") or []
    if not isinstance(cits, list):
        cits = []
    cleaned = []
    for c in cits[:20]:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("chunk_id") or "").strip()
        quote = str(c.get("quote") or "").strip()
        if cid and quote:
            cleaned.append({"chunk_id": cid, "quote": quote[:300]})
    return {"answer": ans or str(raw).strip(), "citations": cleaned}

