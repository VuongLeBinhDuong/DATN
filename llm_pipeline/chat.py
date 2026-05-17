#!/usr/bin/env python3
"""LLM pipeline chat CLI. Chỉ hỗ trợ GraphRAG (Milvus đã bị loại bỏ)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from llm_pipeline.graphrag_query import run_graphrag_query

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Chat CLI: chỉ hỗ trợ GraphRAG (Milvus đã bị loại bỏ)."
    )
    parser.add_argument(
        "--mode",
        choices=["graphrag"],
        default="graphrag",
        help="Chỉ còn graphrag mode.",
    )
    args = parser.parse_args()

    if args.mode in {"rag", "hybrid"}:
        print("Lỗi: rag/hybrid mode đã bị loại bỏ (Milvus không còn được sử dụng).", file=sys.stderr)
        print("Vui lòng dùng: --mode graphrag", file=sys.stderr)
        return 1

    print("Ready. Mode=graphrag")
    while True:
        q = input("\nYou: ").strip()
        if not q:
            continue
        if q.lower() in {"exit", "quit"}:
            break

        print(f"Assistant (GraphRAG):\n{run_graphrag_query(q)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
