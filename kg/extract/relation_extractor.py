from __future__ import annotations

import os
import re
from typing import Any

from kg.extract.json_utils import extract_first_json
from kg.models import RelationRecord, coerce_float
from kg.predicates import normalize_predicate
from llm_pipeline.llm_chat import chat_ollama, chat_openrouter, synthesis_backend


def _llm_call(prompt: str) -> str:
    host = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL") or "llama3.1:8b"
    timeout = int(os.getenv("OLLAMA_TIMEOUT") or "120")
    temperature = float(os.getenv("KG_REL_TEMPERATURE") or "0.1")
    num_predict = int(os.getenv("KG_REL_NUM_PREDICT") or "2048")

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


REL_PROMPT_TEMPLATE = """\
Bạn là hệ thống trích xuất quan hệ cho Knowledge Graph y khoa.

NHIỆM VỤ:
- Chỉ tạo relation giữa các entity có trong danh sách ENTITIES.
- KHÔNG tạo entity mới.
- KHÔNG dùng từ ngoài ENTITIES làm subject/object.
- Nếu không có relation hợp lệ thì trả về [].

CHỈ được dùng predicate sau:
- CAUSES
- TREATS
- TREATED_BY
- INTERACTS_WITH
- PART_OF
- DIAGNOSED_BY
- PREVENTS
- HAS_SIDE_EFFECT
- AFFECTS
- SYMPTOM_OF

QUAN TRỌNG:
- Chỉ trả về JSON array.
- KHÔNG markdown.
- KHÔNG giải thích.
- KHÔNG text ngoài JSON.
- Output phải bắt đầu bằng [ và kết thúc bằng ].

Format:
[
  {{
    "subject": "...",
    "predicate": "...",
    "object": "...",
    "confidence": 0.95
  }}
]

ENTITIES:
{entities}

TEXT:
\"\"\"{text}\"\"\"
"""


def _format_entities(entities: list[dict[str, Any]], max_n: int = 40) -> str:
    lines: list[str] = []
    for e in entities[:max_n]:
        name = str(e.get("canonical_name") or "").strip()
        typ = str(e.get("type") or "").strip()
        if not name:
            continue
        if typ:
            lines.append(f"- {name} ({typ})")
        else:
            lines.append(f"- {name}")
    return "\n".join(lines) if lines else "- (none)"


def extract_relations_from_chunk(chunk_text: str, entities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prompt = REL_PROMPT_TEMPLATE.format(
        entities=_format_entities(entities),
        text=(chunk_text or "")[:8000],
    )
    raw = _llm_call(prompt)
    data = extract_first_json(raw)
    if isinstance(data, dict):
        data = data.get("relations", [])
    if not isinstance(data, list):
        return []
    return [x for x in data if isinstance(x, dict)]


def _norm_key(s: str) -> str:
    t = re.sub(r"\s+", " ", (s or "").strip()).lower()
    return t


def to_relation_records(
    *,
    evidence_chunk_id: str,
    extracted: list[dict[str, Any]],
    entities_for_chunk: list[dict[str, Any]],
) -> list[RelationRecord]:
    # Build name->entity_id lookup using canonical + aliases.
    lookup: dict[str, str] = {}
    for e in entities_for_chunk:
        eid = str(e.get("entity_id") or "").strip()
        cn = str(e.get("canonical_name") or "").strip()
        if eid and cn:
            lookup[_norm_key(cn)] = eid
        aliases = e.get("aliases") or []
        if eid and isinstance(aliases, list):
            for a in aliases:
                aa = str(a or "").strip()
                if aa:
                    lookup.setdefault(_norm_key(aa), eid)

    rels: list[RelationRecord] = []
    for item in extracted:
        subj = str(item.get("subject") or "").strip()
        obj = str(item.get("object") or "").strip()
        pred_raw = str(item.get("predicate") or "").strip()
        if not subj or not obj:
            continue
        sid = lookup.get(_norm_key(subj))
        oid = lookup.get(_norm_key(obj))
        if not sid or not oid or sid == oid:
            continue
        conf = coerce_float(item.get("confidence"), 0.5)
        conf = max(0.0, min(conf, 1.0))
        pred = normalize_predicate(pred_raw)
        if pred == "RELATED_TO" and conf < 0.9:
            continue
        rels.append(
            RelationRecord(
                subject_entity_id=sid,
                object_entity_id=oid,
                predicate=pred,
                confidence=conf,
                evidence_chunk_id=evidence_chunk_id,
            )
        )
    return rels
