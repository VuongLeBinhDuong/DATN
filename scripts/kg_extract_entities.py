from __future__ import annotations

import argparse

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.extract.entity_extractor import extract_entities_from_chunk, to_entity_and_mentions
from kg.extract.regex_entity_extractor import to_records_regex
from kg.extract.implicit_relations import generate_cooccurrence_relations
from kg.neo4j_client import Neo4jKGClient


def _ollama_available() -> bool:
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 11434))
        sock.close()
        return result == 0
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract entities for chunks and write Entity/MENTIONS to Neo4j.")
    ap.add_argument("--limit", type=int, default=50, help="Chunks per batch")
    ap.add_argument("--skip", type=int, default=0, help="Skip chunks")
    ap.add_argument("--doc-id", default=None, help="Optional doc_id filter")
    ap.add_argument(
        "--only-missing",
        action="store_true",
        help="Only process chunks without any MENTIONS edges",
    )
    ap.add_argument(
        "--regex-only",
        action="store_true",
        help="Skip LLM extraction, use regex only (faster, no Ollama required)",
    )
    args = ap.parse_args()

    ollama_ok = _ollama_available()
    if not ollama_ok and not args.regex_only:
        print("⚠️  Ollama not available on localhost:11434")
        print("   Use: python scripts/kg_extract_entities.py --regex-only")
        return 1

    client = Neo4jKGClient()
    fetch = client.fetch_chunks_without_mentions if args.only_missing else client.fetch_chunks
    rows = fetch(limit=args.limit, skip=args.skip, doc_id=args.doc_id)
    if not rows:
        print("No chunks to process.")
        return 0

    all_entities = []
    all_mentions = []
    all_relations = []

    use_llm = not args.regex_only and ollama_ok

    for idx, r in enumerate(rows):
        chunk_id = r["chunk_id"]
        text = r.get("text") or ""
        print(f"[{idx+1}/{len(rows)}] Processing chunk: {chunk_id}")

        ents_llm, ments_llm = [], []

        if use_llm:
            # Try LLM extraction first
            try:
                extracted_llm = extract_entities_from_chunk(text)
                ents_llm, ments_llm = to_entity_and_mentions(chunk_id, extracted_llm)
            except Exception as e:
                if not args.regex_only:
                    print(f"  LLM extraction failed for {chunk_id}: {e}")

        # Fallback: regex extraction for high recall
        ents_regex, ments_regex = to_records_regex(chunk_id, text)

        # Merge: prefer LLM results, add regex as fallback for missing types
        seen_ids = {e.entity_id for e in ents_llm}
        for e in ents_regex:
            if e.entity_id not in seen_ids:
                ents_llm.append(e)
                seen_ids.add(e.entity_id)

        seen_mentions = {(m.chunk_id, m.entity_id) for m in ments_llm}
        for m in ments_regex:
            if (m.chunk_id, m.entity_id) not in seen_mentions:
                ments_llm.append(m)

        all_entities.extend(ents_llm)
        all_mentions.extend(ments_llm)

        # Generate implicit co-occurrence relations to densify graph
        chunk_entities = [{"entity_id": m.entity_id, "confidence": m.confidence} for m in ments_llm]
        implicit_rels = generate_cooccurrence_relations(chunk_id, chunk_entities, confidence_threshold=0.5)
        all_relations.extend(implicit_rels)

    n_e = client.upsert_entities(all_entities)
    n_m = client.upsert_mentions(all_mentions)
    n_r = client.upsert_relations(all_relations) if all_relations else 0

    print(f"Upserted {n_e} entities, {n_m} mentions, {n_r} implicit relations for {len(rows)} chunks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

