"""Tra cứu ảnh thuốc đã crawl (labels.jsonl) + đường dẫn phục vụ qua /api/pill-images/static/."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from medical_records.storage_paths import pill_image_dataset_dir

# Tiền tố URL (FastAPI mount); khớp với llm_pipeline.app
STATIC_PREFIX = "/api/pill-images/static"

# Tên thư mục crawl (slug) thường dùng INN tiếng Anh; map từ đồng nghĩa / tên thường gọi.
PILL_LOOKUP_ALIASES: dict[str, str] = {
    "paracetamol": "acetaminophen",
}


def resolve_pill_lookup_query(q: str) -> str | None:
    """
    Nếu chuỗi có nhắc alias đã biết, trả về slug tra cứu (vd. paracetamol → acetaminophen).
    Không khớp thì None — caller giữ nguyên query gốc.
    """
    low = (q or "").strip().casefold()
    if not low:
        return None
    for alias, canonical in sorted(PILL_LOOKUP_ALIASES.items(), key=lambda x: -len(x[0])):
        if len(alias) < 4:
            continue
        if alias in low:
            return canonical
    return None


def normalize_pill_search_query(q: str) -> str:
    """Chuẩn hóa trước khi chấm điểm khớp slug/drug."""
    r = resolve_pill_lookup_query(q)
    return r if r is not None else (q or "").strip()


def _slug(s: str) -> str:
    t = re.sub(r"[^\w\-]+", "_", (s or "").strip().lower(), flags=re.UNICODE)
    return (t.strip("_") or "drug")[:100]


@lru_cache(maxsize=1)
def _load_all_records() -> list[dict]:
    """Đọc mọi labels.jsonl dưới thư mục dataset."""
    root = pill_image_dataset_dir()
    flat: list[dict] = []
    if not root.is_dir():
        return flat

    for labels_path in sorted(root.rglob("labels.jsonl")):
        rel_parent = labels_path.parent.relative_to(root)
        slug = str(rel_parent).replace("\\", "/").split("/")[0] if str(rel_parent) != "." else ""
        if not slug:
            slug = labels_path.parent.name
        try:
            text = labels_path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            drug = str(row.get("drug") or slug).strip()
            fn = str(row.get("filename") or "").strip()
            if not fn:
                continue
            rec = {
                "drug": drug or slug,
                "slug": slug,
                "filename": fn,
                "source_url": str(row.get("source_url") or row.get("source") or ""),
                "width": row.get("width"),
                "height": row.get("height"),
                "relative_path": f"{slug}/{fn}".replace("\\", "/"),
                "image_url": f"{STATIC_PREFIX}/{slug}/{fn}",
            }
            flat.append(rec)

    return flat


def lookup_pill_images(query: str, *, limit: int = 6) -> list[dict]:
    """
    Tìm ảnh theo tên thuốc / từ khóa (không phân biệt hoa thường).
    Ưu tiên khớp slug thư mục, sau đó khớp chuỗi trong tên drug.

    Nếu câu có **alias đã map** (vd. paracetamol→acetaminophen): chỉ trả ảnh đúng slug/hoạt chất đó,
    không dùng điểm token — tránh “ảnh bừa” khi câu dài nhiễu từ khóa.
    """
    raw = (query or "").strip()
    canonical_from_alias = resolve_pill_lookup_query(raw)
    q = normalize_pill_search_query(raw)
    if not q:
        return []
    ql = q.casefold()
    flat = _load_all_records()
    if not flat:
        return []

    # Khớp chắc theo alias: chỉ đúng thư mục / tên drug đã chuẩn hóa (không fuzzy chéo thuốc).
    if canonical_from_alias:
        cq = canonical_from_alias.casefold()
        strict: list[dict] = []
        for rec in flat:
            slug = (rec.get("slug") or "").casefold()
            drug = str(rec.get("drug") or "").casefold()
            if slug == cq or drug == cq:
                strict.append(dict(rec))
        strict.sort(key=lambda r: (r.get("filename") or ""))
        return strict[:limit]

    scored: list[tuple[int, dict]] = []
    # Câu dài không có alias: bỏ khớp yếu (chỉ vài token +15) để giảm nhiễu.
    min_score = 70 if len(q) > 96 else 50
    for rec in flat:
        slug = rec.get("slug") or ""
        drug = str(rec.get("drug") or "")
        s = 0
        if slug.casefold() == ql:
            s += 100
        elif ql == drug.casefold():
            s += 95
        elif slug.casefold().startswith(ql) or drug.casefold().startswith(ql):
            s += 80
        elif ql in slug.casefold() or ql in drug.casefold():
            s += 50
        else:
            tokens = [t for t in re.split(r"[^\w]+", ql) if len(t) > 2]
            dlow, slow = drug.casefold(), slug.casefold()
            for t in tokens:
                if t in dlow or t in slow:
                    s += 15
        if s >= min_score:
            scored.append((s, rec))

    scored.sort(key=lambda x: (-x[0], x[1].get("filename", "")))
    out: list[dict] = []
    seen: set[str] = set()
    for _score, rec in scored:
        key = rec.get("relative_path") or rec.get("image_url")
        if key in seen:
            continue
        seen.add(str(key))
        out.append(dict(rec))
        if len(out) >= limit:
            break
    return out


def enrich_suggested_medications_with_pill_images(
    medications: list[dict[str, Any]],
    *,
    per_drug_limit: int = 4,
) -> list[dict[str, Any]]:
    """Gắn ``pill_images`` (kết quả :func:`lookup_pill_images`) vào mỗi mục ``suggested_medications``."""
    out: list[dict[str, Any]] = []
    for m in medications:
        d = dict(m)
        name = str(d.get("name") or "").strip()
        d["pill_images"] = lookup_pill_images(name, limit=per_drug_limit) if name else []
        out.append(d)
    return out


def format_pill_image_observation(items: list[dict]) -> str:
    """Văn bản cho Observation (LLM) + có thể parse thêm."""
    if not items:
        return (
            "Không tìm thấy ảnh thuốc trong dataset local cho từ khóa này. "
            "Gợi ý: dùng tên hoạt chất tiếng Anh (vd. acetaminophen, ibuprofen) đúng với thư mục đã crawl."
        )
    lines = [
        f"Có {len(items)} ảnh trong dataset crawl (minh họa, không thay cho nhãn thật):",
    ]
    for it in items:
        lines.append(
            f"- {it['drug']}: file {it['filename']}; nguồn ảnh gốc: {it.get('source_url', '')[:120]}"
        )
    lines.append("")
    lines.append("JSON: " + json.dumps({"pill_images": items}, ensure_ascii=False))
    return "\n".join(lines)


def invalidate_cache() -> None:
    _load_all_records.cache_clear()
