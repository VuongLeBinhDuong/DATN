"""Ingest JSON QA files into Neo4j KG.

Handles ViHealthQA format and similar JSON arrays with question/answer or title/content.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.ingest.chunking import chunk_text_structured
from kg.models import ChunkRecord, DocumentRecord
from kg.neo4j_client import Neo4jKGClient


def _doc_id_from_record(record: dict[str, Any], idx: int) -> str:
    """Generate stable doc_id from record."""
    # Prefer explicit ID fields
    for key in ("topic_id", "id", "doc_id", "uuid"):
        if key in record and record[key]:
            return f"doc_{str(record[key])}"
    # Fallback: hash of title + first 100 chars of content
    title = str(record.get("title") or record.get("question") or f"doc_{idx}")
    content = str(record.get("content") or record.get("answer") or "")[:100]
    h = hashlib.sha1(f"{title}|{content}".encode("utf-8")).hexdigest()[:16]
    return f"doc_{h}"


def _extract_text(record: dict[str, Any]) -> str:
    """Extract full text content from record."""
    parts = []

    # Try various common fields
    if record.get("title"):
        parts.append(f"# {record['title']}")

    if record.get("question"):
        parts.append(f"Câu hỏi: {record['question']}")

    if record.get("content") and record.get("content") != record.get("answer"):
        parts.append(f"Nội dung: {record['content']}")

    if record.get("answer"):
        parts.append(f"Trả lời: {record['answer']}")

    if record.get("text"):
        parts.append(record["text"])

    # If nothing found, use all string fields
    if not parts:
        for k, v in record.items():
            if isinstance(v, str) and len(v) > 20:
                parts.append(f"{k}: {v}")

    return "\n\n".join(parts)


def ingest_json_file(
    json_path: str,
    client: Neo4jKGClient,
    max_chars: int = 2400,
    overlap_chars: int = 200,
) -> dict[str, int]:
    """Ingest a JSON file into Neo4j."""

    path = Path(json_path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Handle both single object and array
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError(f"JSON must be an array or object, got {type(data)}")

    doc_records: list[DocumentRecord] = []
    chunk_records: list[ChunkRecord] = []

    for idx, record in enumerate(data):
        doc_id = _doc_id_from_record(record, idx)
        title = str(record.get("title") or record.get("question") or f"Document {idx}")
        text = _extract_text(record)

        if not text.strip():
            continue

        doc_records.append(DocumentRecord(
            doc_id=doc_id,
            title=title[:200],
            source=f"{path.name}#{idx}",
        ))

        # Chunk the text
        chunks = chunk_text_structured(
            doc_id,
            text,
            is_markdown=False,
            max_chars=max_chars,
            overlap_chars=overlap_chars,
        )

        for c in chunks:
            chunk_records.append(ChunkRecord(
                chunk_id=c.chunk_id,
                doc_id=doc_id,
                text=c.text,
                section_path=c.section_path,
                start_offset=c.start_offset,
                end_offset=c.end_offset,
            ))

    # Bulk insert
    client.upsert_documents(doc_records)
    n_chunks = client.upsert_chunks(chunk_records)

    return {
        "documents": len(doc_records),
        "chunks": n_chunks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest JSON QA files into Neo4j KG")
    ap.add_argument("--input", "-i", required=True, help="JSON file path")
    ap.add_argument("--max-chars", type=int, default=2400, help="Max chars per chunk")
    ap.add_argument("--overlap-chars", type=int, default=200, help="Chunk overlap")
    args = ap.parse_args()

    if not Path(args.input).exists():
        print(f"File not found: {args.input}")
        return 1

    client = Neo4jKGClient()

    try:
        stats = ingest_json_file(
            args.input,
            client,
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
        )
        print(f"Ingested: {stats['documents']} documents, {stats['chunks']} chunks")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
