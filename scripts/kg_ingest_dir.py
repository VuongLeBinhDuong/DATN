from __future__ import annotations

import argparse
from pathlib import Path

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.ingest.chunking import chunk_text_structured
from kg.ingest.loader import load_raw_documents_from_dir
from kg.models import ChunkRecord, DocumentRecord
from kg.neo4j_client import Neo4jKGClient


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest a directory into Neo4j custom KG (Document/Chunk).")
    ap.add_argument("--input-dir", required=True, help="Directory containing source documents")
    ap.add_argument("--max-chars", type=int, default=2400, help="Max chars per chunk")
    ap.add_argument("--overlap-chars", type=int, default=200, help="Chunk overlap in chars")
    args = ap.parse_args()

    docs = load_raw_documents_from_dir(args.input_dir)
    if not docs:
        print("No documents found.")
        return 2

    client = Neo4jKGClient()

    doc_rows: list[DocumentRecord] = []
    chunk_rows: list[ChunkRecord] = []
    for d in docs:
        doc_rows.append(DocumentRecord(doc_id=d.doc_id, title=d.title, source=d.source))
        is_md = Path(d.source).suffix.lower() in (".md", ".markdown")
        chunks = chunk_text_structured(
            d.doc_id,
            d.text,
            is_markdown=is_md,
            max_chars=args.max_chars,
            overlap_chars=args.overlap_chars,
        )
        for c in chunks:
            chunk_rows.append(
                ChunkRecord(
                    chunk_id=c.chunk_id,
                    doc_id=d.doc_id,
                    text=c.text,
                    section_path=c.section_path,
                    start_offset=c.start_offset,
                    end_offset=c.end_offset,
                )
            )

    client.upsert_documents(doc_rows)
    n_chunks = client.upsert_chunks(chunk_rows)
    print(f"Ingested {len(doc_rows)} documents and {n_chunks} chunks from {args.input_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

