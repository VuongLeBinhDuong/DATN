"""Extract text from PDFs (PyMuPDF); optional page subset and normalized 0–1 region crop."""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz  # not bare "fitz" — wrong PyPI package can shadow PyMuPDF


def parse_page_spec(spec: str | None, n_pages: int) -> list[int]:
    """Parse page list like '1-3', '1,4,5', or None for all. Spec is 1-based; returns 0-based indices."""
    if not spec or not spec.strip():
        return list(range(n_pages))
    out: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            lo = max(1, int(a))
            hi = min(n_pages, int(b))
            for p in range(lo, hi + 1):
                out.add(p - 1)
        else:
            p = int(part)
            if 1 <= p <= n_pages:
                out.add(p - 1)
    return sorted(out) if out else list(range(n_pages))


def extract_text_from_pdf(
    path: Path | str,
    *,
    page_spec: str | None = None,
    crop_norm: tuple[float, float, float, float] | None = None,
) -> tuple[str, dict]:
    """
    crop_norm: (x0, y0, x1, y1) in normalized 0–1 coordinates per page (top-left origin).
    Returns (text, meta) with meta keys: n_pages, pages_used, crop_applied.
    """
    p = Path(path)
    doc = fitz.open(p)
    try:
        n = doc.page_count
        indices = parse_page_spec(page_spec, n)
        parts: list[str] = []
        for idx in indices:
            page = doc.load_page(idx)
            r = page.rect
            clip = None
            if crop_norm is not None:
                x0, y0, x1, y1 = crop_norm
                clip = fitz.Rect(
                    float(x0) * r.width,
                    float(y0) * r.height,
                    float(x1) * r.width,
                    float(y1) * r.height,
                )
            if clip is not None:
                t = page.get_text(clip=clip, sort=True)
            else:
                t = page.get_text(sort=True)
            if t.strip():
                parts.append(f"--- Page {idx + 1} ---\n{t.strip()}")
        text = "\n\n".join(parts)
        return text, {
            "n_pages": n,
            "pages_used": [i + 1 for i in indices],
            "crop_applied": crop_norm is not None,
        }
    finally:
        doc.close()
