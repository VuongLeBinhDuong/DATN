#!/usr/bin/env python3
"""CLI: analyze a medical record file: PDF or Excel (extract, compare to reference, optional Ollama)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from medical_records.analyze import analyze_medical_file  # noqa: E402
from medical_records.xlsx_extract import extract_raw_text_from_xlsx, extract_structured_rows_from_xlsx  # noqa: E402

_ALLOWED = {".pdf", ".xlsx", ".xlsm"}
_PREVIEW_CHARS = 600


def main() -> int:
    p = argparse.ArgumentParser(description="Analyze a medical record (PDF or XLSX illustrative pipeline).")
    p.add_argument("path", type=Path, help="Path to .pdf, .xlsx, or .xlsm")
    p.add_argument("--pages", default=None, help='PDF pages: "1-3" or "1,2,5"')
    p.add_argument("--sheet", default=None, help="Excel: single sheet name (omit = all sheets)")
    p.add_argument("--sex", choices=("male", "female"), default=None, help="Sex (for hemoglobin reference)")
    p.add_argument("--no-llm", action="store_true", help="Do not call Ollama (internal reference narrative)")
    p.add_argument(
        "--llm-report-compare",
        action="store_true",
        help="Call Ollama to compare result vs reference printed on the form (grounded; Vietnamese default).",
    )
    p.add_argument(
        "--report-compare-lang",
        default="vi",
        help="Language for report-compare narrative: vi or en (default: vi).",
    )
    p.add_argument(
        "--internal-reference",
        action="store_true",
        help="Legacy: parse labs and compare to config/lab_reference_ranges.json (default: off; use on-form refs).",
    )
    p.add_argument("--json", action="store_true", help="Print JSON to stdout")
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Save full analysis JSON to this path (UTF-8).",
    )
    p.add_argument(
        "--text-out",
        type=Path,
        default=None,
        help="Save raw extracted plain text to this path (UTF-8).",
    )
    p.add_argument(
        "--include-extracted-in-json",
        action="store_true",
        help="Include full extracted_text in JSON (-o / --json); can be large.",
    )
    p.add_argument(
        "--structured-out",
        type=Path,
        default=None,
        help="XLSX only: save each sheet as rows (list of cell strings) to this JSON file.",
    )
    p.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Do not print extraction summary / preview to stdout.",
    )
    args = p.parse_args()
    if not args.path.is_file():
        logger.error("File not found: %s", args.path)
        return 1
    suf = args.path.suffix.lower()
    if suf not in _ALLOWED:
        logger.error("Unsupported suffix: %s", suf)
        return 1
    need_full = args.text_out is not None or args.include_extracted_in_json
    out = analyze_medical_file(
        args.path,
        page_spec=args.pages,
        sheet_name=args.sheet,
        patient_sex=args.sex,
        with_llm=False if args.no_llm else None,
        include_full_text=need_full,
        with_report_compare_llm=args.llm_report_compare,
        report_compare_language=args.report_compare_lang,
        use_internal_reference=args.internal_reference,
    )

    if args.text_out:
        txt = out.pop("extracted_text", None)
        if txt is None:
            txt = ""
        args.text_out.parent.mkdir(parents=True, exist_ok=True)
        args.text_out.write_text(txt, encoding="utf-8")
        logger.info("Wrote extracted text: %s", args.text_out.resolve())
        if suf in (".xlsx", ".xlsm") and os.getenv("MEDICAL_RECORD_SKIP_RAW_EXTRACT", "").strip().lower() not in (
            "1",
            "true",
            "yes",
            "on",
        ):
            raw_txt, _ = extract_raw_text_from_xlsx(args.path, sheet_name=args.sheet)
            raw_path = args.text_out.with_name(f"{args.text_out.stem}_raw.txt")
            raw_path.write_text(raw_txt, encoding="utf-8")
            logger.info("Wrote raw TSV (Excel grid): %s", raw_path.resolve())

    if args.structured_out:
        if suf not in (".xlsx", ".xlsm"):
            logger.error("--structured-out only applies to .xlsx / .xlsm")
            return 2
        args.structured_out.parent.mkdir(parents=True, exist_ok=True)
        blob = extract_structured_rows_from_xlsx(args.path, sheet_name=args.sheet)
        args.structured_out.write_text(json.dumps(blob, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote structured rows: %s", args.structured_out.resolve())

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Wrote JSON: %s", args.output.resolve())

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))  # Keep for JSON output mode
        return 0

    if not args.quiet:
        tp = out.get("text_preview") or ""
        logger.info("=== Extraction summary ===")
        logger.info("format: %s", out.get("format"))
        logger.info("text_length: %s", out.get("text_length"))
        logger.info("extract_meta: %s", out.get("extract_meta"))
        logger.info("plain_text_preview (first %d chars):", _PREVIEW_CHARS)
        print(tp[:_PREVIEW_CHARS] + ("..." if len(tp) > _PREVIEW_CHARS else ""))  # Keep for preview display
        if args.text_out:
            logger.info("full plain text file: %s", args.text_out.resolve())
        else:
            logger.info("full plain text: add --text-out <file.txt> to save everything")
        if suf in (".xlsx", ".xlsm"):
            if args.structured_out:
                logger.info("structured rows (per sheet, per row): %s", args.structured_out.resolve())
            else:
                logger.info("structured rows: add --structured-out <file.json> (keeps each cell per row)")
        logger.info("---")
    logger.info("parsed_labs_count: %s", out["parsed_labs_count"])
    for row in out["comparisons"]:
        print(json.dumps(row, ensure_ascii=False))  # Keep for table output
    if out.get("narrative"):
        print("\n--- narrative (internal reference table) ---\n", out["narrative"])  # Keep for narrative display
    if out.get("narrative_report_compare"):
        print("\n--- narrative (result vs reference on form) ---\n", out["narrative_report_compare"])  # Keep for narrative display
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
