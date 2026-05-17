"""Compare parsed labs to reference config; optional narrative via Ollama."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import requests

from medical_records.lab_parse import parse_labeled_values, to_canonical_value
from medical_records.record_extract import extract_text_from_record
from medical_records.lab_compare_on_form import compare_extracted_report_on_form, format_on_form_lab_for_llm
from medical_records.xlsx_extract import extract_raw_text_from_xlsx
from medical_records.reference_ranges import (
    canonical_match,
    default_reference_path,
    load_reference_config,
    pick_hemoglobin_entry,
)
from medical_records.rag_advice_llm import (
    fetch_graphrag_context,
    llm_extract_reasoning_plus_graphrag_advice,
)
from medical_records.report_compare_llm import llm_compare_result_to_reference_on_report
from medical_records.storage_paths import medical_record_upload_dir
from medical_records.pill_image_store import enrich_suggested_medications_with_pill_images
from medical_records.suggest_meds_extract import extract_suggested_drugs_from_narrative

# When not using config/lab_reference_ranges.json (default: references come from the report itself).
DISCLAIMER_FORM_ONLY = (
    "Khoảng tham chiếu trên phiếu do phòng xét nghiệm in; hệ thống ưu tiên so sánh theo đó "
    "(ví dụ qua chế độ LLM đọc phiếu). File config lab_reference_ranges.json chỉ dùng khi bật so khớp nội bộ."
)


def _skip_raw_xlsx_extract() -> bool:
    return os.getenv("MEDICAL_RECORD_SKIP_RAW_EXTRACT", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _skip_on_form_compare() -> bool:
    return os.getenv("MEDICAL_RECORD_DISABLE_ON_FORM_COMPARE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _classify(value: float, low: float, high: float) -> str:
    if value < low:
        return "below_reference"
    if value > high:
        return "above_reference"
    return "within_reference"


def compare_to_reference(
    labs: list[dict[str, Any]],
    cfg: dict[str, Any],
    *,
    patient_sex: str | None = None,
) -> list[dict[str, Any]]:
    """Match each parsed row to a reference range; hemoglobin uses patient_sex when set."""
    ranges: list[dict[str, Any]] = [
        e for e in cfg.get("ranges", []) if not str(e.get("id", "")).startswith("hemoglobin_")
    ]
    hb_entry = pick_hemoglobin_entry(cfg, patient_sex)
    rows: list[dict[str, Any]] = []
    for lab in labs:
        raw = lab["raw_label"]
        val = lab["value"]
        unit = lab.get("unit")
        matched: dict[str, Any] | None = None
        if hb_entry and canonical_match(raw, hb_entry):
            matched = hb_entry
        else:
            for entry in ranges:
                if canonical_match(raw, entry):
                    matched = entry
                    break
        if not matched:
            rows.append(
                {
                    "raw_label": raw,
                    "value": val,
                    "unit": unit,
                    "reference_id": None,
                    "canonical_value": None,
                    "reference_unit": None,
                    "ref_low": None,
                    "ref_high": None,
                    "status": "unmatched",
                    "comment": "No matching reference entry in config.",
                }
            )
            continue
        canon_val, ref_unit = to_canonical_value(val, unit, matched)
        low = float(matched["low"])
        high = float(matched["high"])
        if canon_val is None:
            rows.append(
                {
                    "raw_label": raw,
                    "value": val,
                    "unit": unit,
                    "reference_id": matched.get("id"),
                    "canonical_value": None,
                    "reference_unit": matched.get("unit"),
                    "ref_low": low,
                    "ref_high": high,
                    "status": "unit_mismatch",
                    "comment": f"Unit conversion needed (canonical: {ref_unit}).",
                }
            )
            continue
        st = _classify(canon_val, low, high)
        note = matched.get("note_gender") or ""
        rows.append(
            {
                "raw_label": raw,
                "value": val,
                "unit": unit,
                "reference_id": matched.get("id"),
                "canonical_value": round(canon_val, 4),
                "reference_unit": ref_unit,
                "ref_low": low,
                "ref_high": high,
                "status": st,
                "comment": "",
                "reference_note": note,
            }
        )
    return rows


def build_llm_summary(
    text_preview: str,
    comparisons: list[dict[str, Any]],
    disclaimer: str,
) -> str | None:
    """Call Ollama chat directly (summary over extract + comparison table)."""
    host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    model = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    timeout = int(os.getenv("OLLAMA_TIMEOUT", "120"))
    lines = []
    for r in comparisons:
        if r.get("status") in ("unmatched", "unit_mismatch"):
            lines.append(f"- {r['raw_label']}: {r['value']} {r.get('unit') or ''} → {r.get('comment')}")
        else:
            lines.append(
                f"- {r['raw_label']}: {r.get('canonical_value')} {r.get('reference_unit')} "
                f"(reference {r.get('ref_low')}-{r.get('ref_high')}) → {r.get('status')}"
            )
    comp_block = "\n".join(lines) if lines else "(No labs matched for automated comparison.)"
    prompt = f"""You are a medical information assistant. Write in English.

{disclaimer}

Extract from the uploaded record, PDF or spreadsheet (may lack context):
---
{text_preview[:6000]}
---

Automated comparison table (may be wrong if extraction or parsing failed):
{comp_block}

Write a brief response in three parts:
1) Summarize values outside the internal reference band (if any); say "per the bundled reference table".
2) What you are unsure about or what data is missing.
3) Practical interpretation; you may suggest appropriate medications and dosing when justified by the extract and comparison.

Avoid definitive diagnosis when evidence is thin; do not invent lab values."""

    try:
        url = host + "/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.2},
        }
        resp = requests.post(url, json=payload, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return (data.get("message", {}) or {}).get("content", "").strip() or None
    except requests.RequestException:
        return None


def analyze_medical_file(
    file_path: Path | str,
    *,
    page_spec: str | None = None,
    crop_norm: tuple[float, float, float, float] | None = None,
    sheet_name: str | None = None,
    patient_sex: str | None = None,
    reference_path: Path | None = None,
    text_preview_max: int = 8000,
    with_llm: bool | None = None,
    include_full_text: bool = False,
    with_report_compare_llm: bool = False,
    report_compare_language: str = "vi",
    use_internal_reference: bool = False,
    save_extract_to: Path | str | None = None,
    with_on_form_compare: bool = True,
) -> dict[str, Any]:
    """
    Full pipeline: PDF or XLSX → plain text → optional parse/compare vs ``lab_reference_ranges.json``.

    By default (``use_internal_reference=False``) we **do not** compare against the JSON file, because
    real lab reports already print reference ranges; use ``with_report_compare_llm`` to compare via LLM
    on the extracted text.

    Set ``use_internal_reference=True`` to enable legacy: parse ``Label: value`` lines and compare to config.

    ``page_spec`` / ``crop_norm`` apply only to PDF. ``sheet_name`` applies only to Excel.
    with_llm=None follows USE_OLLAMA env var (only used for the internal-reference narrative).
    If ``include_full_text`` is True, the return dict includes ``extracted_text`` (full extraction).
    If ``with_report_compare_llm`` is True, runs a separate LLM pass that compares result vs
    reference **as printed on the report** (grounded in extracted text; Vietnamese by default).

    Luôn (khi có văn bản trích) gọi một lượt LLM kèm **GraphRAG** (Neo4j, ``config/neo4j.json``): suy luận trên
    phiếu chỉ từ bản trích; phần tư vấn bám **ngữ cảnh đồ thị** (``medical_records/rag_advice_llm.py``).
    ``MEDICAL_RECORD_GRAPHRAG_TOP_K`` điều chỉnh số nút truy vấn (mặc định 6).

    For **Excel** (``.xlsx`` / ``.xlsm``), when ``save_extract_to`` is set, a companion **raw** file
    is also written next to it: same stem with ``_raw.txt`` (tab-separated cells per row). Disable
    with env ``MEDICAL_RECORD_SKIP_RAW_EXTRACT=1``.

    When ``with_on_form_compare`` is True (default), runs **pure-Python** comparison of numeric
    results vs reference strings printed on the form (see ``lab_compare_on_form``). No LLM required.
    Disable with ``with_on_form_compare=False`` or env ``MEDICAL_RECORD_DISABLE_ON_FORM_COMPARE=1``.
    """
    path = Path(file_path)
    text, meta = extract_text_from_record(
        path,
        page_spec=page_spec,
        crop_norm=crop_norm,
        sheet_name=sheet_name,
    )
    extract_saved_path: str | None = None
    extract_raw_saved_path: str | None = None
    if save_extract_to:
        out = Path(save_extract_to)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        extract_saved_path = str(out.resolve())
        if path.suffix.lower() in (".xlsx", ".xlsm") and not _skip_raw_xlsx_extract():
            raw_text, _raw_meta = extract_raw_text_from_xlsx(path, sheet_name=sheet_name)
            raw_out = out.with_name(f"{out.stem}_raw.txt")
            raw_out.write_text(raw_text, encoding="utf-8")
            extract_raw_saved_path = str(raw_out.resolve())
    if use_internal_reference:
        cfg = load_reference_config(reference_path or default_reference_path())
        disclaimer = cfg.get("disclaimer", "")
        labs = parse_labeled_values(text)
        comparisons = compare_to_reference(labs, cfg, patient_sex=patient_sex)
    else:
        disclaimer = DISCLAIMER_FORM_ONLY
        labs = []
        comparisons = []
    on_form_lab: dict[str, Any] | None = None
    _run_lab_compare = with_on_form_compare and text.strip() and not _skip_on_form_compare()
    if _run_lab_compare:
        on_form_lab = compare_extracted_report_on_form(text, patient_sex=patient_sex)
    preview = text[:text_preview_max] + ("..." if len(text) > text_preview_max else "")
    do_llm = with_llm if with_llm is not None else os.getenv("USE_OLLAMA", "").lower() in ("1", "true", "yes")
    narrative = None
    if do_llm and use_internal_reference:
        narrative = build_llm_summary(preview, comparisons, disclaimer)
    narrative_report_compare = None
    if with_report_compare_llm and text.strip():
        narrative_report_compare = llm_compare_result_to_reference_on_report(
            text,
            language=report_compare_language,
        )
    narrative_extract_and_graphrag = None
    graphrag_advice_meta: dict[str, Any] | None = None
    if text.strip():
        try:
            gr_top_k = int(os.getenv("MEDICAL_RECORD_GRAPHRAG_TOP_K", "6"))
        except ValueError:
            gr_top_k = 6
        gr_top_k = max(1, min(gr_top_k, 48))
        gr_query_source = text
        if on_form_lab and on_form_lab.get("abnormal"):
            labels = ", ".join(str(r.get("label", "")) for r in on_form_lab["abnormal"])
            gr_query_source = f"{text}\n\n[Ưu tiên tư vấn các chỉ số bất thường: {labels}]"
        gr_block, graphrag_advice_meta = fetch_graphrag_context(
            gr_query_source,
            top_k=gr_top_k,
            graphrag_query_chars=None,
        )
        lab_for_llm = (
            format_on_form_lab_for_llm(on_form_lab, language=report_compare_language)
            if on_form_lab is not None
            else ""
        )
        narrative_extract_and_graphrag = llm_extract_reasoning_plus_graphrag_advice(
            text,
            gr_block,
            language=report_compare_language,
            lab_compare_block=lab_for_llm or None,
            meta_out=graphrag_advice_meta,
        )
        if graphrag_advice_meta is not None:
            graphrag_advice_meta["lab_compare_block_chars"] = len(lab_for_llm)
    suggested_medications = extract_suggested_drugs_from_narrative(narrative_extract_and_graphrag)
    suggested_medications = enrich_suggested_medications_with_pill_images(suggested_medications)
    upload_root = medical_record_upload_dir()
    result: dict[str, Any] = {
        "file": str(path.resolve()),
        "format": path.suffix.lower().lstrip("."),
        "reference_mode": "internal_config" if use_internal_reference else "on_form_only",
        "extract_meta": meta,
        "text_length": len(text),
        "text_preview": preview,
        "parsed_labs_count": len(labs),
        "comparisons": comparisons,
        "disclaimer": disclaimer,
        "narrative": narrative,
        "narrative_report_compare": narrative_report_compare,
        "narrative_extract_and_graphrag": narrative_extract_and_graphrag,
        "suggested_medications": suggested_medications,
        "graphrag_advice_meta": graphrag_advice_meta,
        "upload_dir_hint": str(upload_root),
        "extract_saved_path": extract_saved_path,
        "extract_raw_saved_path": extract_raw_saved_path,
        "on_form_lab": on_form_lab,
    }
    if include_full_text:
        result["extracted_text"] = text
    return result


# Backward-compatible name
analyze_pdf_path = analyze_medical_file
