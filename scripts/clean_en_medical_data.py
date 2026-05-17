#!/usr/bin/env python3
"""
Clean medical_reference_en.json - giảm size và chuẩn hóa.

Lọc theo tiêu chí:
- Bỏ content quá ngắn hoặc quá dài
- Bỏ duplicate (by content hash)
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


def clean_en_medical(
    input_path: Path,
    output_path: Path,
    *,
    min_content_chars: int = 50,
    max_content_chars: int = 10000,
    max_records: int | None = 10000,
    dedup: bool = True,
) -> dict[str, int]:
    stats = {
        "input": 0,
        "output": 0,
        "drop_short": 0,
        "drop_long": 0,
        "drop_dup": 0,
        "drop_limit": 0,
    }

    print(f"Reading {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    stats["input"] = len(data)
    seen_content: set[str] = set()
    cleaned: list[dict[str, Any]] = []

    for item in data:
        content = str(item.get("content") or "").strip()
        content_len = len(content)

        # Filter by length
        if content_len < min_content_chars:
            stats["drop_short"] += 1
            continue
        if content_len > max_content_chars:
            stats["drop_long"] += 1
            continue

        # Deduplicate by content (first 300 chars)
        if dedup:
            content_key = content[:300].lower().strip()
            if content_key in seen_content:
                stats["drop_dup"] += 1
                continue
            seen_content.add(content_key)

        # Limit total records
        if max_records and len(cleaned) >= max_records:
            remaining = stats["input"] - len(cleaned) - sum(
                v for k, v in stats.items() if k not in ("input", "output")
            )
            stats["drop_limit"] = remaining
            break

        # Keep minimal fields
        cleaned.append({
            "topic_id": item.get("topic_id", ""),
            "title": str(item.get("title", content[:240]))[:240],
            "content": content[:80000],  # Hard limit
            "source_org": str(item.get("source_org", ""))[:256],
            "lang": "en",
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
    parser = argparse.ArgumentParser(description="Clean English medical data for indexing.")
    parser.add_argument("--input", type=Path, default=REPO_ROOT / "data" / "medical_reference_en.json")
    parser.add_argument("--output", type=Path, default=None, help="Default: overwrite input")
    parser.add_argument("--max-records", type=int, default=10000, help="Max records (0 = all)")
    parser.add_argument("--no-dedup", action="store_true", help="Skip dedup")
    parser.add_argument("--min-chars", type=int, default=50, help="Min content length")
    parser.add_argument("--max-chars", type=int, default=10000, help="Max content length")
    args = parser.parse_args()

    max_records = None if args.max_records <= 0 else args.max_records
    output_path = args.output if args.output else args.input

    stats = clean_en_medical(
        args.input,
        output_path,
        max_records=max_records,
        dedup=not args.no_dedup,
        min_content_chars=args.min_chars,
        max_content_chars=args.max_chars,
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
