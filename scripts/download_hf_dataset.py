#!/usr/bin/env python3
"""
Download HuggingFace dataset: medalpaca/medical_meadow_wikidoc_patient_information

Requires: pip install datasets

Usage:
  python scripts/download_hf_dataset.py --dataset medalpaca/medical_meadow_wikidoc_patient_information --output data/hf_medical_meadow.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def download_dataset(dataset_name: str, output_path: Path, split: str = "train", limit: int | None = None) -> int:
    """Download HuggingFace dataset and save as JSON."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("Error: 'datasets' library not installed. Run: pip install datasets")
        return 1
    
    print(f"Downloading dataset: {dataset_name} (split={split})")
    ds = load_dataset(dataset_name, split=split)
    
    if limit and limit > 0:
        ds = ds.select(range(min(limit, len(ds))))
    
    records: list[dict[str, Any]] = []
    for i, item in enumerate(ds):
        # Convert to serializable dict
        record = {
            "id": i,
            **{k: str(v) if v is not None else "" for k, v in item.items()}
        }
        records.append(record)
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(records)} records to: {output_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Download HuggingFace medical dataset")
    parser.add_argument(
        "--dataset",
        default="medalpaca/medical_meadow_wikidoc_patient_information",
        help="HuggingFace dataset name",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "data" / "hf_medical_meadow.json",
        help="Output JSON file path",
    )
    parser.add_argument("--split", default="train", help="Dataset split (train/test/validation)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of records (for testing)")
    args = parser.parse_args()
    
    return download_dataset(args.dataset, args.output, args.split, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
