#!/usr/bin/env python3
"""
Clean crawled reference JSON data for RAG / GraphRAG input.

What it does:
- remove obvious Spanish pages/content
- remove records with empty or too-short content
- remove records with severe mojibake corruption
- deduplicate by normalized source_url, then by (topic_id, title)
- keep output schema unchanged

Default behavior:
- Read ``medical_reference_diseases.json`` and ``medical_reference_drugs.json`` under ``--data-dir``
- Replace each file atomically with cleaned content (old file content is fully replaced)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

REPO_ROOT = Path(__file__).resolve().parents[1]

SPANISH_URL_HINTS = (
    "/spanish/",
    "medlineplus.gov/spanish/",
)
SPANISH_TITLE_HINTS = (
    "en español",
    "español",
)
SPANISH_CONTENT_HINTS = (
    " los ",
    " las ",
    " este ",
    " esta ",
    " medicamento ",
    " también ",
    " también en inglés ",
    " también en ingles ",
    " para ",
    " con ",
    " de ",
)
MOJIBAKE_CHARS = ("Ã", "Â", "�")


def normalize_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    parsed = parsed._replace(query="", fragment="")
    return urlunparse(parsed)


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def count_mojibake_chars(text: str) -> int:
    if not text:
        return 0
    return sum(text.count(ch) for ch in MOJIBAKE_CHARS)


def is_spanish_like(url: str, title: str, content: str) -> bool:
    u = (url or "").lower()
    t = (title or "").lower()
    c = f" {(content or '').lower()} "

    if any(h in u for h in SPANISH_URL_HINTS):
        return True
    if any(h in t for h in SPANISH_TITLE_HINTS):
        return True

    hits = sum(1 for h in SPANISH_CONTENT_HINTS if h in c)
    return hits >= 2


def clean_records(
    records: list[dict[str, Any]],
    *,
    min_content_chars: int,
    max_mojibake_chars: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    stats = {
        "input_rows": len(records),
        "drop_empty_content": 0,
        "drop_too_short": 0,
        "drop_spanish_like": 0,
        "drop_mojibake": 0,
        "drop_dup_url": 0,
        "drop_dup_topic_title": 0,
        "output_rows": 0,
    }

    cleaned: list[dict[str, Any]] = []
    seen_url: set[str] = set()
    seen_topic_title: set[tuple[str, str]] = set()

    for rec in records:
        content = normalize_space(str(rec.get("content", "")))
        title = normalize_space(str(rec.get("title", "")))
        source_url = normalize_url(str(rec.get("source_url", "")))
        topic_id = normalize_space(str(rec.get("topic_id", ""))).lower()

        if not content:
            stats["drop_empty_content"] += 1
            continue
        if len(content) < min_content_chars:
            stats["drop_too_short"] += 1
            continue
        if is_spanish_like(source_url, title, content):
            stats["drop_spanish_like"] += 1
            continue
        if count_mojibake_chars(content) > max_mojibake_chars:
            stats["drop_mojibake"] += 1
            continue

        if source_url and source_url in seen_url:
            stats["drop_dup_url"] += 1
            continue
        tt_key = (topic_id, title.lower())
        if title and tt_key in seen_topic_title:
            stats["drop_dup_topic_title"] += 1
            continue

        rec["content"] = content
        rec["title"] = title
        rec["source_url"] = source_url
        if "lang" in rec:
            rec["lang"] = "en"

        cleaned.append(rec)
        if source_url:
            seen_url.add(source_url)
        if title:
            seen_topic_title.add(tt_key)

    stats["output_rows"] = len(cleaned)
    return cleaned, stats


def read_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} is not a JSON array")
    return [x for x in data if isinstance(x, dict)]


def atomic_replace_json(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    """Write JSON then atomically replace target (removes old file content on success)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(list(rows), ensure_ascii=False, indent=2)
    fd, tmp_name = tempfile.mkstemp(
        suffix=".json.tmp",
        prefix=path.name + ".",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        Path(tmp_name).replace(path)
    except Exception:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def process_file(
    input_path: Path,
    output_path: Path,
    min_chars: int,
    max_mojibake: int,
    *,
    replace_in_place: bool,
) -> None:
    if not input_path.is_file():
        print(f"Skip (missing): {input_path}")
        return

    rows = read_json(input_path)
    cleaned, stats = clean_records(
        rows,
        min_content_chars=min_chars,
        max_mojibake_chars=max_mojibake,
    )

    if replace_in_place and output_path.resolve() == input_path.resolve():
        atomic_replace_json(output_path, cleaned)
    else:
        if output_path.is_file():
            output_path.unlink()
        atomic_replace_json(output_path, cleaned)

    print(f"\n=== {input_path.name} -> {output_path.name} ===")
    for k, v in stats.items():
        print(f"{k}: {v}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean reference crawl JSON files in data/.")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=REPO_ROOT / "data",
        help="Directory containing medical_reference_diseases.json and medical_reference_drugs.json",
    )
    parser.add_argument(
        "--diseases-name",
        default="medical_reference_diseases.json",
        help="Filename for diseases corpus",
    )
    parser.add_argument(
        "--drugs-name",
        default="medical_reference_drugs.json",
        help="Filename for drugs corpus",
    )
    parser.add_argument(
        "--no-in-place",
        action="store_true",
        help="Do not overwrite data-dir; write cleaned files to --out-dir (default: graphrag/input)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="If set with --no-in-place, write cleaned files here",
    )
    parser.add_argument("--min-content-chars", type=int, default=300)
    parser.add_argument(
        "--max-mojibake-chars",
        type=int,
        default=8,
        help="Drop row if mojibake char count exceeds this value.",
    )
    args = parser.parse_args()
    in_place = not args.no_in_place

    data_dir: Path = args.data_dir
    diseases_in = data_dir / args.diseases_name
    drugs_in = data_dir / args.drugs_name

    if in_place:
        d_out, dr_out = diseases_in, drugs_in
    else:
        out = args.out_dir or (REPO_ROOT / "graphrag" / "input")
        d_out = out / args.diseases_name
        dr_out = out / args.drugs_name

    process_file(
        diseases_in,
        d_out,
        args.min_content_chars,
        args.max_mojibake_chars,
        replace_in_place=in_place,
    )
    process_file(
        drugs_in,
        dr_out,
        args.min_content_chars,
        args.max_mojibake_chars,
        replace_in_place=in_place,
    )

    out_note = data_dir if in_place else (args.out_dir or REPO_ROOT / "graphrag" / "input")
    print(f"\nDone. Clean files: {out_note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
