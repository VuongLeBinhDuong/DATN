from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import sys

# Ensure repo root is on sys.path when running as a script.
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from kg.neo4j_client import Neo4jKGClient


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _export_paged(
    *,
    fetch: Callable[..., list[dict[str, Any]]],
    out_path: Path,
    page_size: int,
) -> int:
    total = 0
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        skip = 0
        while True:
            rows = fetch(limit=page_size, skip=skip)
            if not rows:
                break
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            total += len(rows)
            skip += len(rows)
            if len(rows) < page_size:
                break
    return total


def main() -> int:
    ap = argparse.ArgumentParser(description="Export custom KG artifacts from Neo4j to JSONL files.")
    ap.add_argument(
        "--out-dir",
        default=str(Path("kg") / "kg_artifacts"),
        help="Output directory (default: kg/kg_artifacts)",
    )
    ap.add_argument("--page-size", type=int, default=2000, help="Rows per page for export")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    client = Neo4jKGClient()

    counts = {}
    counts["documents"] = _export_paged(fetch=client.export_documents, out_path=out_dir / "documents.jsonl", page_size=min(args.page_size, 5000))
    counts["chunks"] = _export_paged(fetch=client.export_chunks, out_path=out_dir / "chunks.jsonl", page_size=min(args.page_size, 2000))
    counts["entities"] = _export_paged(fetch=client.export_entities, out_path=out_dir / "entities.jsonl", page_size=min(args.page_size, 5000))
    counts["mentions"] = _export_paged(fetch=client.export_mentions, out_path=out_dir / "mentions.jsonl", page_size=min(args.page_size, 10000))
    counts["relations"] = _export_paged(fetch=client.export_relations, out_path=out_dir / "relations.jsonl", page_size=min(args.page_size, 10000))

    meta = {"format": "kg_artifacts_v1", "counts": counts}
    _write_jsonl(out_dir / "_meta.jsonl", [meta])

    print(f"Exported artifacts to {out_dir}")
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

