from __future__ import annotations

import argparse
import json

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.answer import synthesize_answer_with_citations
from kg.neo4j_client import Neo4jKGClient
from retrieval.graph_first import graph_first_retrieve


def main() -> int:
    ap = argparse.ArgumentParser(description="Graph-first KG-RAG query (Neo4j).")
    ap.add_argument("--question", required=True, help="User question")
    ap.add_argument("--hops", type=int, default=2, help="Graph expansion hops (0-3)")
    ap.add_argument("--seed-k", type=int, default=12, help="Top seed entities from fulltext")
    ap.add_argument("--evidence-k", type=int, default=8, help="Top evidence chunks")
    ap.add_argument("--json", action="store_true", help="Output JSON instead of pretty text")
    ap.add_argument("--debug", action="store_true", help="Include retrieval debug trace")
    args = ap.parse_args()

    client = Neo4jKGClient()
    r = graph_first_retrieve(
        args.question,
        client=client,
        top_seed_entities=args.seed_k,
        hops=args.hops,
        evidence_k=args.evidence_k,
    )
    out = synthesize_answer_with_citations(args.question, r.evidence_chunks)
    payload = {
        "answer": out.get("answer"),
        "citations": out.get("citations", []),
    }
    if args.debug:
        payload["debug"] = r.debug
        payload["subgraph_summary"] = {
            "entities": len((r.subgraph.get("entities") or [])),
            "edges": len((r.subgraph.get("edges") or [])),
        }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    print(payload["answer"] or "")
    if payload["citations"]:
        print("\n--- Citations ---")
        for c in payload["citations"]:
            print(f"- {c.get('chunk_id')}: {c.get('quote')}")
    if args.debug:
        print("\n--- Debug ---")
        print(json.dumps(payload.get("debug"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

