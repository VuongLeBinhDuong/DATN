#!/usr/bin/env python3
"""Clean Vietnamese medical reference datasets before indexing."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

NOISE_TERMS = (
    "khuyen mai",
    "khuyến mãi",
    "dat hang",
    "đặt hàng",
    "giao hang",
    "giao hàng",
    "tai ung dung",
    "tải ứng dụng",
    "duoc my pham",
    "dược mỹ phẩm",
    "thuc pham chuc nang",
    "thực phẩm chức năng",
)

ALLOWED_PATH_HINTS = (
    "/thuoc/",
    "/thanh-phan/",
    "/benh/",
    "/tieu-duong-dai-thao-duong/",
)


def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def has_noise(text: str) -> bool:
    t = norm_text(text)
    return any(k in t for k in NOISE_TERMS)


def keep_record(r: dict[str, Any], *, min_len: int, max_len: int) -> tuple[bool, str]:
    content = str(r.get("content") or "").strip()
    source_url = str(r.get("source_url") or "").strip().lower()
    if not content:
        return False, "empty_content"
    if len(content) < min_len:
        return False, "too_short"
    if len(content) > max_len:
        return False, "too_long"
    if has_noise(content) or has_noise(source_url):
        return False, "noise_terms"
    if source_url and ("hellobacsi.com" in source_url or "longchau.com.vn" in source_url):
        if not any(h in source_url for h in ALLOWED_PATH_HINTS):
            return False, "path_not_allowed"
    return True, "ok"


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        key = norm_text(str(r.get("source_url") or "")) + "||" + norm_text(str(r.get("title") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def clean_file(input_path: Path, output_path: Path, *, min_len: int, max_len: int) -> dict[str, int]:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{input_path} must be a JSON list.")
    kept: list[dict[str, Any]] = []
    dropped = 0
    for x in raw:
        if not isinstance(x, dict):
            dropped += 1
            continue
        ok, _reason = keep_record(x, min_len=min_len, max_len=max_len)
        if ok:
            kept.append(x)
        else:
            dropped += 1
    kept = dedupe_rows(kept)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(kept, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"input": len(raw), "kept": len(kept), "dropped": dropped}


def main() -> int:
    p = argparse.ArgumentParser(description="Clean Vietnamese medical datasets.")
    p.add_argument("--data-dir", type=Path, default=Path("data"))
    p.add_argument("--min-len", type=int, default=180)
    p.add_argument("--max-len", type=int, default=12000)
    args = p.parse_args()

    files = [
        "medical_reference_vi_qa.json",
    ]
    for src in files:
        in_path = args.data_dir / src
        if not in_path.is_file():
            print(f"[SKIP] Missing {in_path}")
            continue
        stats = clean_file(
            in_path,
            in_path,  # in-place overwrite
            min_len=args.min_len,
            max_len=args.max_len,
        )
        print(f"[OK] {src}: input={stats['input']} kept={stats['kept']} dropped={stats['dropped']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

