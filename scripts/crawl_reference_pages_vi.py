#!/usr/bin/env python3
"""
Tải corpus QA y khoa tiếng Việt từ Hugging Face (ViHealthQA + tương tự) → data/medical_reference_vi_qa.json.

Chạy:
  python scripts/crawl_reference_pages_vi.py
  python scripts/crawl_reference_pages_vi.py --qa-max-rows-per-split 500
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

HF_QA_DATASETS = [
    ("tarudesu/ViHealthQA", "ViHealthQA"),
    # ("hungnm/vietnamese-medical-qa", "VNMedicalQA"),
    # ("Dqdung205/medical-vietnamese-qa", "MedicalVietnameseQA"),
    # ("hungsvdut2k2/vietnamese-medical-chat-data", "VietnameseMedicalChatData"),
    # ("quannguyen204/vietnamese-medical-article-corpus" , "VietnameseMedicalCorpus"),
]


def fetch_hf_qa_records(*, max_rows_per_split: int | None = None, dedup_by_question: bool = True) -> list[dict[str, Any]]:
    from datasets import load_dataset  # type: ignore

    rows: list[dict[str, Any]] = []
    seen_questions: set[str] = set()
    now = datetime.now(timezone.utc).isoformat()
    for dataset_id, source_name in HF_QA_DATASETS:
        try:
            ds_dict = load_dataset(dataset_id)
        except Exception as exc:  # noqa: BLE001
            print(f"[WARN] Skip {dataset_id}: {exc}")
            continue
        for split, ds in ds_dict.items():
            dup_count = 0
            for i, item in enumerate(ds):
                if max_rows_per_split is not None and i >= max_rows_per_split:
                    break
                q = str(item.get("question") or "").strip().lower()
                if dedup_by_question and q:
                    if q in seen_questions:
                        dup_count += 1
                        continue
                    seen_questions.add(q)
                _append_qa_row(rows, source_name, split, i, item, now)
            print(f"[OK] {dataset_id}:{split} -> {min(len(ds), max_rows_per_split or len(ds))} rows" + (f" (bo qua {dup_count} cau hoi trung)" if dup_count > 0 else ""))
    return rows


def _append_qa_row(
    rows: list[dict[str, Any]],
    source_name: str,
    split: str,
    i: int,
    item: dict[str, Any],
    now: str,
) -> None:
    q = str(item.get("question") or "").strip()
    a = str(item.get("answer") or "").strip()
    link = str(item.get("link") or item.get("url") or "").strip()
    if not q or not a:
        return
    rows.append(
        {
            "topic_id": f"{source_name.lower()}_{split}_{i}",
            "topic_type": "qa",
            "question": q,
            "answer": a,
            "source_org": source_name,
            "source_url": link,
            "title": q[:240],
            "content": a,
            "content_type": "qa_pair",
            "lang": "vi",
            "split": str(split),
            "crawled_at": now,
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Vietnamese medical QA datasets to JSON.")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "data")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Default: medical_reference_vi_qa.json under --output-dir",
    )
    parser.add_argument(
        "--qa-max-rows-per-split",
        type=int,
        default=0,
        help="Limit rows per split per dataset (0 = all).",
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Khong loai bo cau hoi trung lap.",
    )
    args = parser.parse_args()
    qa_limit = None if args.qa_max_rows_per_split <= 0 else args.qa_max_rows_per_split

    out_dir = args.output_dir
    if out_dir.exists() and out_dir.is_file():
        print(f"[WARN] --output-dir la file ({out_dir}), dung {REPO_ROOT / 'data'}")
        out_dir = REPO_ROOT / "data"
    out = args.output or (out_dir / "medical_reference_vi_qa.json")
    print("=== Fetch QA datasets (ViHealthQA + similar) ===")
    rows = fetch_hf_qa_records(max_rows_per_split=qa_limit, dedup_by_question=not args.no_dedup)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} records to: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
