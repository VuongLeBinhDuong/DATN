from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import sys

# Ensure repo root is on sys.path when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.models import ChunkRecord, DocumentRecord, EntityRecord, MentionRecord, RelationRecord
from kg.neo4j_client import Neo4jKGClient


def _iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.is_file():
        return []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        t = (line or "").strip()
        if not t:
            continue
        yield json.loads(t)


def _batched(it: Iterable[Any], n: int) -> Iterable[list[Any]]:
    batch: list[Any] = []
    for x in it:
        batch.append(x)
        if len(batch) >= n:
            yield batch
            batch = []
    if batch:
        yield batch


@dataclass(frozen=True)
class ImportCounts:
    documents: int = 0
    chunks: int = 0
    entities: int = 0
    mentions: int = 0
    relations: int = 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Import custom KG artifacts (JSONL) into Neo4j.")
    ap.add_argument(
        "--in-dir",
        default=str(Path("kg") / "kg_artifacts"),
        help="Artifacts directory (default: kg/kg_artifacts)",
    )
    ap.add_argument("--clear", action="store_true", help="Clear existing custom KG nodes/edges before import")
    ap.add_argument("--batch", type=int, default=1000, help="Batch size for UNWIND upserts")
    ap.add_argument("--apply-schema", action="store_true", help="Apply kg/schema.cypher before import")
    args = ap.parse_args()

    in_dir = Path(args.in_dir)
    client = Neo4jKGClient()

    if args.apply_schema:
        n = client.apply_schema(Path("kg") / "schema.cypher")
        print(f"Applied schema statements: {n}")

    if args.clear:
        stats = client.clear_custom_kg()
        print("Cleared custom KG:", json.dumps(stats, ensure_ascii=False))

    counts = ImportCounts()

    docs_path = in_dir / "documents.jsonl"
    chunks_path = in_dir / "chunks.jsonl"
    entities_path = in_dir / "entities.jsonl"
    mentions_path = in_dir / "mentions.jsonl"
    relations_path = in_dir / "relations.jsonl"

    # Documents
    for batch in _batched(_iter_jsonl(docs_path), args.batch):
        rows = [
            DocumentRecord(
                doc_id=str(r.get("doc_id") or ""),
                title=(str(r.get("title")) if r.get("title") is not None else None),
                source=(str(r.get("source")) if r.get("source") is not None else None),
                created_at=None,
            )
            for r in batch
            if str(r.get("doc_id") or "").strip()
        ]
        counts = ImportCounts(documents=counts.documents + client.upsert_documents(rows), chunks=counts.chunks, entities=counts.entities, mentions=counts.mentions, relations=counts.relations)

    # Chunks
    for batch in _batched(_iter_jsonl(chunks_path), max(200, min(args.batch, 1000))):
        rows = []
        for r in batch:
            cid = str(r.get("chunk_id") or "").strip()
            did = str(r.get("doc_id") or "").strip()
            txt = str(r.get("text") or "")
            if not cid or not did or not txt.strip():
                continue
            rows.append(
                ChunkRecord(
                    chunk_id=cid,
                    doc_id=did,
                    text=txt,
                    section_path=(str(r.get("section_path")) if r.get("section_path") is not None else None),
                    start_offset=(int(r["start_offset"]) if r.get("start_offset") is not None else None),
                    end_offset=(int(r["end_offset"]) if r.get("end_offset") is not None else None),
                    created_at=None,
                )
            )
        counts = ImportCounts(documents=counts.documents, chunks=counts.chunks + client.upsert_chunks(rows), entities=counts.entities, mentions=counts.mentions, relations=counts.relations)

    # Entities
    for batch in _batched(_iter_jsonl(entities_path), args.batch):
        rows = []
        for r in batch:
            eid = str(r.get("entity_id") or "").strip()
            cn = str(r.get("canonical_name") or "").strip()
            if not eid or not cn:
                continue
            aliases = r.get("aliases") or []
            if not isinstance(aliases, list):
                aliases = []
            rows.append(
                EntityRecord(
                    entity_id=eid,
                    canonical_name=cn,
                    type=(str(r.get("type")) if r.get("type") is not None else None),
                    aliases=[str(a) for a in aliases if str(a).strip()],
                    created_at=None,
                )
            )
        counts = ImportCounts(documents=counts.documents, chunks=counts.chunks, entities=counts.entities + client.upsert_entities(rows), mentions=counts.mentions, relations=counts.relations)

    # Mentions
    for batch in _batched(_iter_jsonl(mentions_path), max(500, min(args.batch, 5000))):
        rows = []
        for r in batch:
            cid = str(r.get("chunk_id") or "").strip()
            eid = str(r.get("entity_id") or "").strip()
            if not cid or not eid:
                continue
            rows.append(
                MentionRecord(
                    chunk_id=cid,
                    entity_id=eid,
                    confidence=float(r.get("confidence") or 0.5),
                    start_char=(int(r["start_char"]) if r.get("start_char") is not None else None),
                    end_char=(int(r["end_char"]) if r.get("end_char") is not None else None),
                )
            )
        counts = ImportCounts(documents=counts.documents, chunks=counts.chunks, entities=counts.entities, mentions=counts.mentions + client.upsert_mentions(rows), relations=counts.relations)

    # Relations
    for batch in _batched(_iter_jsonl(relations_path), max(500, min(args.batch, 5000))):
        rows = []
        for r in batch:
            sid = str(r.get("subject_entity_id") or "").strip()
            oid = str(r.get("object_entity_id") or "").strip()
            pred = str(r.get("predicate") or "").strip()
            if not sid or not oid or not pred:
                continue
            rows.append(
                RelationRecord(
                    subject_entity_id=sid,
                    object_entity_id=oid,
                    predicate=pred,
                    confidence=float(r.get("confidence") or 0.5),
                    evidence_chunk_id=(str(r.get("evidence_chunk_id")) if r.get("evidence_chunk_id") else None),
                )
            )
        counts = ImportCounts(documents=counts.documents, chunks=counts.chunks, entities=counts.entities, mentions=counts.mentions, relations=counts.relations + client.upsert_relations(rows))

    print("Imported counts:", json.dumps(counts.__dict__, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

