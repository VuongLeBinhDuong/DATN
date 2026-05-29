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


def run_ocr_on_page(page) -> str:
    """Render page to an image and run OCR using pytesseract or easyocr if available."""
    try:
        import pytesseract  # type: ignore
        from PIL import Image
        import io
        
        pix = page.get_pixmap(dpi=150)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        text = pytesseract.image_to_string(img, lang="vie+eng")
        return text
    except ImportError:
        try:
            import easyocr  # type: ignore
            import numpy as np
            import io
            from PIL import Image
            
            pix = page.get_pixmap(dpi=150)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))
            img_np = np.array(img)
            
            # Initialize reader (caches models for 'vi' and 'en')
            reader = easyocr.Reader(['vi', 'en'], gpu=False)
            results = reader.readtext(img_np, detail=0)
            return "\n".join(results)
        except Exception:
            return ""
    except Exception:
        return ""


def extract_text_from_pdf(
    path: Path | str,
    *,
    page_spec: str | None = None,
    crop_norm: tuple[float, float, float, float] | None = None,
) -> tuple[str, dict]:
    """
    crop_norm: (x0, y0, x1, y1) in normalized 0–1 coordinates per page (top-left origin).
    Returns (text, meta) with meta keys: n_pages, pages_used, crop_applied, ocr_fallback_applied.
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
        
        # Detect if PDF is likely scanned (empty text or extremely low density)
        ocr_fallback_applied = False
        is_scanned_pdf_warning = False
        
        if not text.strip() or len(text.strip()) < 15 * len(indices):
            ocr_parts = []
            ocr_success = False
            for idx in indices:
                page = doc.load_page(idx)
                ocr_text = run_ocr_on_page(page)
                if ocr_text.strip():
                    ocr_parts.append(f"--- Page {idx + 1} (OCR Fallback) ---\n{ocr_text.strip()}")
                    ocr_success = True
            
            if ocr_success:
                text = "\n\n".join(ocr_parts)
                ocr_fallback_applied = True
            else:
                is_scanned_pdf_warning = True
                
        return text, {
            "n_pages": n,
            "pages_used": [i + 1 for i in indices],
            "crop_applied": crop_norm is not None,
            "ocr_fallback_applied": ocr_fallback_applied,
            "is_scanned_pdf_warning": is_scanned_pdf_warning,
        }
    finally:
        doc.close()
