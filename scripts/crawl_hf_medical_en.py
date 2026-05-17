#!/usr/bin/env python3
"""
Tải corpus y khoa tiếng Anh từ Hugging Face 
-> data/medical_reference_en.json

Datasets:
  - medalpaca/medical_meadow_wikidoc_patient_information
  - gamino/wiki_medical_terms

Chạy:
  python scripts/crawl_hf_medical_en.py
  python scripts/crawl_hf_medical_en.py --max-rows-per-split 500
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

HF_EN_DATASETS = [
    ("medalpaca/medical_meadow_wikidoc_patient_information", "MedicalMeadowWikidoc"),
    ("gamino/wiki_medical_terms", "WikiMedicalTerms"),
]


def fetch_hf_records(*, max_rows_per_split: int | None = None, dedup_by_content: bool = True) -> list[dict[str, Any]]:
    from datasets import load_dataset  # type: ignore

    rows: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()
    
    for dataset_id, source_name in HF_EN_DATASETS:
        try:
            ds_dict = load_dataset(dataset_id, trust_remote_code=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Skip {dataset_id}: {exc}")
            continue
            
        for split, ds in ds_dict.items():
            dup_count = 0
            for i, item in enumerate(ds):
                if max_rows_per_split is not None and i >= max_rows_per_split:
                    break
                    
                # Lấy content từ các field khác nhau tùy dataset
                content = _extract_content(item, dataset_id)
                if not content:
                    continue
                    
                # Dedup by content hash (first 200 chars)
                content_key = content[:200].lower().strip()
                if dedup_by_content and content_key:
                    if content_key in seen_content:
                        dup_count += 1
                        continue
                    seen_content.add(content_key)
                    
                _append_row(rows, source_name, split, i, item, content, now)
                
            print(f"[OK] {dataset_id}:{split} -> {min(len(ds), max_rows_per_split or len(ds))} rows" + 
                  (f" (dup: {dup_count})" if dup_count > 0 else ""))
    return rows


def _extract_content(item: dict[str, Any], dataset_id: str) -> str:
    """Extract content based on dataset schema."""
    if "medical_meadow" in dataset_id:
        # instruction + input + output format
        parts = []
        if item.get("instruction"):
            parts.append(str(item["instruction"]))
        if item.get("input"):
            parts.append(str(item["input"]))
        if item.get("output"):
            parts.append(str(item["output"]))
        return "\n\n".join(parts)
    elif "wiki_medical" in dataset_id:
        # term + definition format
        term = str(item.get("term") or item.get("name") or "").strip()
        definition = str(item.get("definition") or item.get("description") or "").strip()
        if term and definition:
            return f"{term}\n\n{definition}"
        return definition or term
    else:
        # Generic: join all text fields
        texts = []
        for v in item.values():
            if isinstance(v, str) and len(v) > 10:
                texts.append(v)
        return "\n".join(texts)


def _append_row(
    rows: list[dict[str, Any]],
    source_name: str,
    split: str,
    i: int,
    item: dict[str, Any],
    content: str,
    now: str,
) -> None:
    # Extract title
    title = (
        item.get("instruction", "")[:200] or
        item.get("term", "")[:200] or
        item.get("name", "")[:200] or
        content[:100]
    )
    
    rows.append({
        "topic_id": f"{source_name.lower()}_{split}_{i}",
        "topic_type": "medical_en",
        "source_org": source_name,
        "title": title,
        "content": content,
        "content_type": "medical_text",
        "lang": "en",
        "split": str(split),
        "crawled_at": now,
    })


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch English medical datasets to JSON.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument("--output", type=Path, default=None,
                        help="Default: medical_reference_en.json under --output-dir")
    parser.add_argument("--max-rows-per-split", type=int, default=0,
                        help="Limit rows per split (0 = all)")
    parser.add_argument("--no-dedup", action="store_true", help="Skip deduplication")
    args = parser.parse_args()

    max_rows = args.max_rows_per_split if args.max_rows_per_split > 0 else None
    records = fetch_hf_records(
        max_rows_per_split=max_rows,
        dedup_by_content=not args.no_dedup,
    )

    out_path = args.output or (args.output_dir / "medical_reference_en.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(records)} records to: {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
