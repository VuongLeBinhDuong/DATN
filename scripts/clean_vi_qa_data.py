#!/usr/bin/env python3
"""
Clean medical_reference_vi_qa.json - giảm size từ 786MB xuống.

Lọc theo tiêu chí:
- Bỏ Q/A quá ngắn hoặc quá dài
- Bỏ duplicate câu hỏi (case-insensitive)
- Giới hạn số lượng records
- Chỉ giữ các trường cần thiết cho indexing
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def clean_vi_qa(
    input_path: Path,
    output_path: Path,
    *,
    min_q_chars: int = 10,
    max_q_chars: int = 500,
    min_a_chars: int = 30,
    max_a_chars: int = 5000,
    max_records: int | None = 10000,
    dedup: bool = True,
) -> dict[str, int]:
    stats = {
        "input": 0,
        "output": 0,
        "drop_short_q": 0,
        "drop_long_q": 0,
        "drop_short_a": 0,
        "drop_long_a": 0,
        "drop_dup_q": 0,
        "drop_limit": 0,
    }

    print(f"Reading {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats["input"] = len(data)
    seen_questions: set[str] = set()
    cleaned: list[dict[str, Any]] = []

    for item in data:
        q = str(item.get("question") or "").strip()
        a = str(item.get("answer") or "").strip()

        q_len = len(q)
        a_len = len(a)

        # Filter by length
        if q_len < min_q_chars:
            stats["drop_short_q"] += 1
            continue
        if q_len > max_q_chars:
            stats["drop_long_q"] += 1
            continue
        if a_len < min_a_chars:
            stats["drop_short_a"] += 1
            continue
        if a_len > max_a_chars:
            stats["drop_long_a"] += 1
            continue

        # Deduplicate
        if dedup:
            q_lower = q.lower()
            if q_lower in seen_questions:
                stats["drop_dup_q"] += 1
                continue
            seen_questions.add(q_lower)

        # Limit total records
        if max_records and len(cleaned) >= max_records:
            stats["drop_limit"] += stats["input"] - len(cleaned) - sum(
                v for k, v in stats.items() if k not in ("input", "output")
            )
            break

        # Keep minimal fields
        cleaned.append({
            "topic_id": item.get("topic_id", ""),
            "title": q[:240],
            "content": a[:60000],  # Giới hạn content
            "source_url": str(item.get("source_url") or "")[:2048],
            "source_org": str(item.get("source_org") or "")[:256],
            "lang": "vi",
        })

    stats["output"] = len(cleaned)

    # Atomic write
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json.tmp", dir=str(output_path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cleaned, f, ensure_ascii=False, indent=2)
        Path(tmp).replace(output_path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise

    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean vi_qa data for indexing.")
    parser.add_argument("--input", type=Path, default=REPO_ROOT / "data" / "medical_reference_vi_qa.json")
    parser.add_argument("--output", type=Path, default=None, help="Default: ghi de len file input")
    parser.add_argument("--max-records", type=int, default=10000, help="Max records to keep (0 = all)")
    parser.add_argument("--no-dedup", action="store_true", help="Skip deduplication")
    parser.add_argument("--min-a-chars", type=int, default=30, help="Min answer length")
    parser.add_argument("--max-a-chars", type=int, default=5000, help="Max answer length")
    args = parser.parse_args()

    max_records = None if args.max_records <= 0 else args.max_records
    output_path = args.output if args.output else args.input

    stats = clean_vi_qa(
        args.input,
        output_path,
        max_records=max_records,
        dedup=not args.no_dedup,
        min_a_chars=args.min_a_chars,
        max_a_chars=args.max_a_chars,
    )

    print("\n=== Cleaning Stats ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Show size reduction
    in_size = args.input.stat().st_size / (1024 * 1024)
    out_size = output_path.stat().st_size / (1024 * 1024)
    print(f"\nSize: {in_size:.1f} MB → {out_size:.1f} MB ({out_size/in_size*100:.1f}%)")
    print(f"Output: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
