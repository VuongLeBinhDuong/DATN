"""Dispatch PDF vs Excel to a unified plain-text representation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from medical_records.pdf_extract import extract_text_from_pdf
from medical_records.xlsx_extract import extract_text_from_xlsx


def extract_text_from_record(
    path: Path | str,
    *,
    page_spec: str | None = None,
    crop_norm: tuple[float, float, float, float] | None = None,
    sheet_name: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    PDF: page_spec / crop_norm passed through.
    XLSX/XLSM: sheet_name selects one sheet; omit for all sheets.
    """
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".pdf":
        return extract_text_from_pdf(p, page_spec=page_spec, crop_norm=crop_norm)
    if suf in (".xlsx", ".xlsm"):
        return extract_text_from_xlsx(p, sheet_name=sheet_name)
    raise ValueError(f"Unsupported medical record format: {suf} (use .pdf, .xlsx, .xlsm)")
