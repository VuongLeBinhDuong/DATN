"""FastAPI routes: upload PDF or Excel medical records for analysis."""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from medical_records.analyze import analyze_medical_file
from medical_records.reference_ranges import default_reference_path, load_reference_config
from medical_records.storage_paths import medical_record_extract_dir, medical_record_upload_dir

router = APIRouter()

MAX_BYTES = int(os.getenv("MEDICAL_RECORD_MAX_UPLOAD_MB", "15")) * 1024 * 1024

_ALLOWED = {".pdf", ".xlsx", ".xlsm"}


@router.get("/pill-images")
def pill_images_search(q: str = "", limit: int = 8):
    """Debug / gallery: tra cứu ảnh thuốc trong dataset (``PILL_IMAGE_DATA_DIR``)."""
    from medical_records.pill_image_store import lookup_pill_images

    try:
        lim = max(1, min(int(limit), 40))
    except (TypeError, ValueError):
        lim = 8
    items = lookup_pill_images((q or "").strip(), limit=lim)
    return {"query": q, "count": len(items), "items": items}


@router.get("/lab-reference")
def lab_reference_info():
    """Optional legacy JSON (used only when use_internal_reference=true)."""
    cfg = load_reference_config()
    return {
        "version": cfg.get("version"),
        "disclaimer": cfg.get("disclaimer"),
        "n_ranges": len(cfg.get("ranges", [])),
        "config_path": str(default_reference_path()),
    }


@router.post("/analyze")
async def analyze_medical_record(
    file: UploadFile = File(...),
    pages: str | None = Form(None),
    sheet_name: str | None = Form(None),
    patient_sex: str | None = Form(None),
    use_llm: str | None = Form(None),
    llm_report_compare: str | None = Form(None),
    report_compare_language: str | None = Form(None),
    use_internal_reference: str | None = Form(None),
    crop_x0: float | None = Form(None),
    crop_y0: float | None = Form(None),
    crop_x1: float | None = Form(None),
    crop_y1: float | None = Form(None),
):
    """
    Upload a medical record. Default: **no** comparison to ``lab_reference_ranges.json`` (references on the form).

    Formats: ``.pdf``, ``.xlsx``, ``.xlsm``.

    - **PDF**: ``pages`` (e.g. ``1-3``), ``crop_*`` optional normalized 0–1 rectangle.
    - **Excel**: optional ``sheet_name`` (one sheet); omit to read all sheets.
    - **llm_report_compare**: ``true`` — LLM compares result vs reference **printed on the form**.
    - **report_compare_language**: ``vi`` or ``en`` (optional).
    - **use_internal_reference**: ``true`` — legacy: parse numbers and compare to ``config/lab_reference_ranges.json``.
    - Phân tích luôn kèm **GraphRAG** (Neo4j) + Ollama khi có văn bản trích; không có tùy chọn RAG khác.

    Response always includes **on_form_lab** when extraction yields formatted Excel lab lines: numeric
    comparison vs reference printed on the form (pure Python; no LLM). Use **patient_sex** (``male`` / ``female``)
    for Nam/Nữ ranges; otherwise sex may be inferred from the extract header.
    """
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    base_name = Path(file.filename).name
    if base_name.startswith("~$"):
        raise HTTPException(
            400,
            "Đây là file tạm (~$) của Excel khi đang mở file gốc. "
            "Đóng Excel và tải file .xlsx chính, không phải file ~$.",
        )
    suffix = Path(file.filename).suffix.lower()
    if suffix not in _ALLOWED:
        raise HTTPException(400, "Only .pdf, .xlsx, .xlsm are accepted")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, f"File exceeds {MAX_BYTES // (1024 * 1024)} MB")
    if suffix == ".pdf":
        if not data.startswith(b"%PDF"):
            raise HTTPException(400, "Not a valid PDF")
    else:
        if not data.startswith(b"PK"):
            raise HTTPException(400, "Not a valid Excel Open XML workbook")

    crop_norm = None
    if None not in (crop_x0, crop_y0, crop_x1, crop_y1):
        crop_norm = (crop_x0, crop_y0, crop_x1, crop_y1)
        for c in crop_norm:
            if c < 0 or c > 1:
                raise HTTPException(400, "crop_* must be in [0, 1]")

    upload_root = medical_record_upload_dir()
    upload_root.mkdir(parents=True, exist_ok=True)
    extract_dir = medical_record_extract_dir()
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    out_path = upload_root / safe_name
    extract_path: Path | None = None
    if extract_dir is not None:
        extract_dir.mkdir(parents=True, exist_ok=True)
        extract_path = extract_dir / f"{Path(safe_name).stem}_extract.txt"
    tmp: str | None = None
    try:
        tmp_fd, tmp = tempfile.mkstemp(suffix=suffix)
        os.close(tmp_fd)
        Path(tmp).write_bytes(data)
        llm_flag: bool | None
        if use_llm is None or use_llm.strip() == "":
            llm_flag = None
        else:
            llm_flag = use_llm.strip().lower() in ("1", "true", "yes", "on")
        report_cmp = (
            llm_report_compare is not None
            and llm_report_compare.strip() != ""
            and llm_report_compare.strip().lower() in ("1", "true", "yes", "on")
        )
        rlang = (report_compare_language or "").strip() or "vi"
        is_llm_disabled = os.getenv("MEDICAL_RECORD_DISABLE_LLM", "").strip().lower() in ("1", "true", "yes", "on")
        if use_internal_reference is None or use_internal_reference.strip() == "":
            internal_ref = (suffix == ".pdf") or is_llm_disabled
        else:
            internal_ref = use_internal_reference.strip().lower() in ("1", "true", "yes", "on")
        sheet = (sheet_name or "").strip() or None
        result = await asyncio.to_thread(
            analyze_medical_file,
            tmp,
            page_spec=pages,
            crop_norm=crop_norm,
            sheet_name=sheet,
            patient_sex=patient_sex,
            with_llm=llm_flag,
            with_report_compare_llm=report_cmp,
            report_compare_language=rlang,
            use_internal_reference=internal_ref,
            save_extract_to=extract_path,
        )
        # Windows: Path.replace() fails across drives (e.g. Temp on C:, repo on D:).
        shutil.move(tmp, out_path)
        tmp = None
        result["stored_path"] = str(out_path)
        result["file"] = file.filename
        return result
    finally:
        if tmp and Path(tmp).is_file():
            Path(tmp).unlink(missing_ok=True)