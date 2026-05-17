from __future__ import annotations

import argparse

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.extract.relation_extractor import extract_relations_from_chunk, to_relation_records
from kg.neo4j_client import Neo4jKGClient


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract relations between entities per chunk into Neo4j.")
    ap.add_argument("--limit", type=int, default=25, help="Chunks per batch (relations are more expensive)")
    ap.add_argument("--skip", type=int, default=0, help="Skip chunks")
    ap.add_argument("--doc-id", default=None, help="Optional doc_id filter")
    ap.add_argument(
        "--only-missing",
        action="store_true",
        help="Only process chunks without relations attributed to them (by evidence_chunk_id)",
    )
    args = ap.parse_args()

    client = Neo4jKGClient()
    fetch = client.fetch_chunks_without_relations if args.only_missing else client.fetch_chunks
    chunks = fetch(limit=args.limit, skip=args.skip, doc_id=args.doc_id)
    if not chunks:
        print("No chunks to process.")
        return 0

    all_rels = []
    for idx, c in enumerate(chunks):
        chunk_id = c.get("chunk_id", "")
        print(f"[{idx+1}/{len(chunks)}] Processing chunk: {chunk_id}")
        cid = c["chunk_id"]
        entities = client.fetch_entities_for_chunk(cid)
        if len(entities) < 2:
            continue
        extracted = extract_relations_from_chunk(c.get("text") or "", entities)
        rels = to_relation_records(evidence_chunk_id=cid, extracted=extracted, entities_for_chunk=entities)
        all_rels.extend(rels)

    n = client.upsert_relations(all_rels)
    print(f"Upserted {n} relations from {len(chunks)} chunks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

