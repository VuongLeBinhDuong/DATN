from __future__ import annotations

import hashlib
import os
import re
from typing import Any

from kg.extract.json_utils import extract_first_json
from kg.models import EntityRecord, MentionRecord, coerce_float
from llm_pipeline.llm_chat import chat_ollama, chat_openrouter, synthesis_backend


def _normalize_name(name: str) -> str:
    t = (name or "").strip()
    t = re.sub(r"\s+", " ", t)
    t = t.strip(" \t\r\n\"'`.,;:()[]{}")
    return t


def _entity_id(canonical_name: str, typ: str | None) -> str:
    key = f"{(typ or '').strip().lower()}|{canonical_name.strip().lower()}"
    h = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"ent_{h}"


def _llm_call(prompt: str) -> str:
    host = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
    timeout = int(os.getenv("OLLAMA_TIMEOUT") or "120")
    temperature = float(os.getenv("KG_EXTRACT_TEMPERATURE") or "0.1")
    num_predict = int(os.getenv("KG_EXTRACT_NUM_PREDICT") or "2048")

    backend = synthesis_backend()
    if backend == "openrouter":
        or_model = os.getenv("OPENROUTER_MODEL") or None
        max_tok = min(num_predict, 4096)
        return chat_openrouter(prompt, model=or_model, timeout=timeout, temperature=temperature, max_tokens=max_tok)

    return chat_ollama(
        prompt,
        host=host,
        model=model,
        timeout=timeout,
        temperature=temperature,
        num_predict=num_predict,
    )


ENTITY_PROMPT_TEMPLATE = """\
Bạn là hệ thống trích xuất thực thể cho Knowledge Graph y khoa.

Nhiệm vụ: từ đoạn văn bản dưới đây, hãy trích xuất danh sách thực thể quan trọng theo hướng ưu tiên recall.

Yêu cầu:
- Trả về DUY NHẤT một JSON array.
- Mỗi phần tử là object có keys:
  - name: string (tên thực thể như xuất hiện hoặc tên chuẩn hoá)
  - type: string (một trong: Disease, Symptom, Drug, Treatment, Test, Anatomy, Chemical, Guideline, Other)
  - aliases: array[string] (có thể rỗng)
  - confidence: number trong [0,1]
- Không bịa thực thể không có trong text.

TEXT:
\"\"\"{text}\"\"\"
"""


def extract_entities_from_chunk(chunk_text: str) -> list[dict[str, Any]]:
    prompt = ENTITY_PROMPT_TEMPLATE.format(text=(chunk_text or "")[:8000])
    raw = _llm_call(prompt)
    data = extract_first_json(raw)
    if not isinstance(data, list):
        raise ValueError("entity extraction must return a JSON array")
    return [x for x in data if isinstance(x, dict)]


def to_entity_and_mentions(chunk_id: str, extracted: list[dict[str, Any]]) -> tuple[list[EntityRecord], list[MentionRecord]]:
    entities: list[EntityRecord] = []
    mentions: list[MentionRecord] = []

    seen_eids: set[str] = set()
    for item in extracted:
        name = _normalize_name(str(item.get("name") or ""))
        if not name:
            continue
        typ = _normalize_name(str(item.get("type") or "Other")) or "Other"
        aliases_raw = item.get("aliases") or []
        aliases: list[str] = []
        if isinstance(aliases_raw, list):
            for a in aliases_raw:
                aa = _normalize_name(str(a or ""))
                if aa and aa.lower() != name.lower():
                    aliases.append(aa)

        conf = coerce_float(item.get("confidence"), 0.5)
        conf = max(0.0, min(conf, 1.0))

        eid = _entity_id(name, typ)
        if eid not in seen_eids:
            seen_eids.add(eid)
            entities.append(EntityRecord(entity_id=eid, canonical_name=name, type=typ, aliases=aliases))

        mentions.append(MentionRecord(chunk_id=chunk_id, entity_id=eid, confidence=conf))

    return entities, mentions

