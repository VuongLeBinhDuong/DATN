from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.neo4j_client import Neo4jKGClient
from retrieval.graph_first import graph_first_retrieve


def _iter_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        t = (line or "").strip()
        if not t:
            continue
        rows.append(json.loads(t))
    return rows


def _hit(gold: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
    gold_chunk_id = (gold.get("gold_chunk_id") or "").strip()
    if gold_chunk_id:
        return any((c.get("chunk_id") or "") == gold_chunk_id for c in evidence)

    needle = (gold.get("gold_contains") or "").strip()
    if needle:
        return any(needle.lower() in (c.get("text") or "").lower() for c in evidence)

    # If no gold provided, can't score.
    return False


def _bucket(debug: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    if not debug.get("seed_entity_ids"):
        return "seed_empty"
    if not evidence:
        return "evidence_empty"
    if debug.get("evidence_from_edges", 0) == 0 and debug.get("evidence_from_mentions", 0) > 0:
        return "relations_sparse"
    return "retrieved_but_missed"


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate custom KG graph-first retrieval recall@K.")
    ap.add_argument("--dataset", required=True, help="Path to JSONL dataset")
    ap.add_argument("--k", type=int, default=8, help="Evidence top-K to score")
    ap.add_argument("--hops", type=int, default=2, help="Graph expansion hops")
    ap.add_argument("--seed-k", type=int, default=12, help="Seed entities from fulltext")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of samples (0=all)")
    args = ap.parse_args()

    ds = _iter_jsonl(Path(args.dataset))
    if args.limit and args.limit > 0:
        ds = ds[: args.limit]
    if not ds:
        print("Empty dataset.")
        return 2

    client = Neo4jKGClient()
    ok = 0
    buckets = Counter()
    for i, row in enumerate(ds, start=1):
        q = (row.get("question") or "").strip()
        if not q:
            continue
        r = graph_first_retrieve(
            q,
            client=client,
            top_seed_entities=args.seed_k,
            hops=args.hops,
            evidence_k=args.k,
        )
        if _hit(row, r.evidence_chunks):
            ok += 1
        else:
            buckets[_bucket(r.debug, r.evidence_chunks)] += 1

        if i % 10 == 0:
            print(f"Processed {i}/{len(ds)}...")

    total = len(ds)
    recall = ok / max(1, total)
    print("\n=== KG Retrieval Eval ===")
    print(f"Samples: {total}")
    print(f"Recall@{args.k}: {recall:.3f} ({ok}/{total})")
    if buckets:
        print("\n--- Error buckets (misses) ---")
        for k, v in buckets.most_common():
            print(f"{k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

