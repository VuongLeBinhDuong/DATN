"""Generate implicit relations from entity co-occurrence.

When graph is sparse (few explicit REL edges), create implicit CO_OCCURS_WITH
relations based on entities appearing in same chunk/sentence.
"""
from __future__ import annotations

from typing import Any

from kg.models import RelationRecord
from kg.predicates import normalize_predicate


def generate_cooccurrence_relations(
    chunk_id: str,
    entities: list[dict[str, Any]],
    confidence_threshold: float = 0.5,
) -> list[RelationRecord]:
    """Create CO_OCCURS_WITH relations for all entity pairs in same chunk.

    This densifies the graph when explicit relations are sparse.
    """
    rels: list[RelationRecord] = []
    n = len(entities)

    for i in range(n):
        for j in range(i + 1, n):
            e1 = entities[i]
            e2 = entities[j]

            sid = str(e1.get("entity_id") or "").strip()
            oid = str(e2.get("entity_id") or "").strip()

            if not sid or not oid or sid == oid:
                continue

            # Use average confidence
            c1 = float(e1.get("confidence") or 0.5)
            c2 = float(e2.get("confidence") or 0.5)
            conf = (c1 + c2) / 2.0

            if conf < confidence_threshold:
                continue

            rels.append(RelationRecord(
                subject_entity_id=sid,
                object_entity_id=oid,
                predicate="CO_OCCURS_WITH",
                confidence=conf,
                evidence_chunk_id=chunk_id,
            ))

    return rels
