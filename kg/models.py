from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DocumentRecord:
    doc_id: str
    title: str | None = None
    source: str | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class ChunkRecord:
    chunk_id: str
    doc_id: str
    text: str
    section_path: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class EntityRecord:
    entity_id: str
    canonical_name: str
    type: str | None = None
    aliases: list[str] | None = None
    created_at: datetime | None = None


@dataclass(frozen=True)
class MentionRecord:
    chunk_id: str
    entity_id: str
    confidence: float = 0.5
    start_char: int | None = None
    end_char: int | None = None


@dataclass(frozen=True)
class RelationRecord:
    subject_entity_id: str
    object_entity_id: str
    predicate: str
    confidence: float = 0.5
    evidence_chunk_id: str | None = None


def now_iso() -> str:
    # Neo4j can store string or datetime; we keep ISO string for simplicity/portability.
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def coerce_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default

