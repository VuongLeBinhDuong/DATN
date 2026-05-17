"""So sánh kết quả với tham chiếu in trên phiếu — không dùng LLM.

Chỉ xử lý các dòng đúng định dạng do ``xlsx_extract._format_lab_table_row`` tạo ra
(có cụm \"Tham chiếu in trên phiếu (không phải kết quả bệnh nhân)\"). PDF / văn bản
tự do có thể không khớp pattern.
"""

from __future__ import annotations

import re
from typing import Any

# Dòng đã format từ Excel (medical_records/xlsx_extract.py)
_REF_MARKER = "Tham chiếu in trên phiếu (không phải kết quả bệnh nhân):"

_SEX_IN_TEXT = re.compile(
    r"Giới\s*tính\s*:\s*([^|\n]+)",
    re.IGNORECASE,
)

_QUAL = re.compile(
    r"(?i)^(negative|positive|trace|reactive|non[-\s]?reactive|"
    r"normal|abnormal|present|absent|âm\s*tính|dương\s*tính)(\b|$)"
)


def _to_float(s: str) -> float:
    return float(s.replace(",", ".").replace(" ", "").strip())


def normalize_sex(s: str | None) -> str | None:
    if not s:
        return None
    x = str(s).lower().strip()
    if x in ("female", "f", "nữ", "nu", "2"):
        return "female"
    if x in ("male", "m", "nam", "1"):
        return "male"
    return None


def infer_sex_from_extract(text: str) -> str | None:
    m = _SEX_IN_TEXT.search(text)
    if not m:
        return None
    frag = m.group(1).strip().lower()
    if "nữ" in frag or "female" in frag:
        return "female"
    if "nam" in frag and "nữ" not in frag:
        return "male"
    return None


def _parse_float_result(value_str: str) -> float | None:
    t = (value_str or "").strip()
    if not t:
        return None
    if _QUAL.match(t.split()[0] if t else ""):
        return None
    try:
        return _to_float(t)
    except ValueError:
        return None


def _parse_formatted_line(line: str) -> dict[str, Any] | None:
    if _REF_MARKER not in line:
        return None
    parts = [p.strip() for p in line.split("|")]
    if len(parts) < 2:
        return None
    first = parts[0]
    idx = first.find(":")
    if idx <= 0:
        return None
    label = first[:idx].strip()
    value_str = first[idx + 1 :].strip()
    unit = ""
    ref = ""
    machine = ""
    for p in parts[1:]:
        if p.startswith("Đơn vị:"):
            unit = p.replace("Đơn vị:", "", 1).strip()
        elif p.startswith(_REF_MARKER):
            ref = p.replace(_REF_MARKER, "", 1).strip()
        elif p.startswith("Máy:"):
            machine = p.replace("Máy:", "", 1).strip()
    if not ref:
        return None
    return {
        "label": label,
        "value_str": value_str,
        "unit": unit,
        "reference_raw": ref,
        "machine": machine,
    }


def _extract_gender_closed_intervals(r: str) -> dict[str, tuple[float, float] | None]:
    out: dict[str, tuple[float, float] | None] = {"male": None, "female": None}
    for m in re.finditer(r"(?i)(Nam|Nữ)\s*:?\s*([\d.,]+)\s*[-–]\s*([\d.,]+)", r):
        g = m.group(1).lower()
        lo, hi = _to_float(m.group(2)), _to_float(m.group(3))
        if "nam" in g:
            out["male"] = (lo, hi)
        else:
            out["female"] = (lo, hi)
    return out


def _extract_gender_upper(r: str) -> dict[str, tuple[float, bool] | None]:
    """Mỗi giới: (ngưỡng trên, strict_lt) với strict_lt True nghĩa là dấu <."""
    out: dict[str, tuple[float, bool] | None] = {"male": None, "female": None}
    for m in re.finditer(
        r"(?i)(Nam|Nữ)\s*:?\s*(?:\([^)]*\)\s*)?([<≤])\s*([\d.,]+)",
        r,
    ):
        g = m.group(1).lower()
        sym = m.group(2)
        bound = _to_float(m.group(3))
        strict = sym in ("<",)
        if "nam" in g:
            out["male"] = (bound, strict)
        else:
            out["female"] = (bound, strict)
    return out


def _classify_interval(v: float, lo: float, hi: float) -> str:
    if lo <= v <= hi:
        return "within"
    if v < lo:
        return "low"
    return "high"


def _classify_upper(v: float, bound: float, strict: bool) -> str:
    """Bình thường khi giá trị dưới ngưỡng (vd. < 35)."""
    if strict:
        if v < bound:
            return "within"
        return "high"
    if v <= bound:
        return "within"
    return "high"


def _classify_lower(v: float, bound: float, strict: bool) -> str:
    """Bình thường khi giá trị trên ngưỡng (vd. HDL > 0.9)."""
    if strict:
        if v > bound:
            return "within"
        return "low"
    if v >= bound:
        return "within"
    return "low"


def classify_value_against_reference(
    value: float,
    ref: str,
    sex: str | None,
) -> tuple[str, str | None]:
    """
    Trả về (status, lý do khi skipped/unparsed).

    status: ``within`` | ``high`` | ``low`` | ``skipped`` | ``unparsed``
    """
    r = ref.strip().replace("\n", " ")
    if not r:
        return "skipped", "Không có tham chiếu"

    g = _extract_gender_closed_intervals(r)
    if g["male"] or g["female"]:
        if g["male"] and g["female"]:
            if sex is None:
                return "skipped", "Cần giới tính (Nam/Nữ)"
            rng = g["female"] if sex == "female" else g["male"]
        elif g["female"]:
            rng = g["female"]
            if sex == "male":
                return "skipped", "Chỉ có tham chiếu Nữ"
        else:
            rng = g["male"]  # type: ignore[assignment]
            if sex == "female":
                return "skipped", "Chỉ có tham chiếu Nam"
        lo, hi = rng  # type: ignore[misc]
        return _classify_interval(value, lo, hi), None

    gu = _extract_gender_upper(r)
    if gu["male"] or gu["female"]:
        if gu["male"] and gu["female"]:
            if sex is None:
                return "skipped", "Cần giới tính (Nam/Nữ)"
            rng = gu["female"] if sex == "female" else gu["male"]
        elif gu["female"]:
            rng = gu["female"]
            if sex == "male":
                return "skipped", "Chỉ có tham chiếu Nữ"
        else:
            rng = gu["male"]  # type: ignore[assignment]
            if sex == "female":
                return "skipped", "Chỉ có tham chiếu Nam"
        bound, strict = rng  # type: ignore[misc]
        return _classify_upper(value, bound, strict), None

    m = re.match(r"^\s*([<≤])\s*([\d.,]+)\s*$", r)
    if m:
        sym = m.group(1)
        bound = _to_float(m.group(2))
        strict = sym in ("<",)
        return _classify_upper(value, bound, strict), None

    m = re.match(r"^\s*([>≥])\s*([\d.,]+)\s*$", r)
    if m:
        sym = m.group(1)
        bound = _to_float(m.group(2))
        strict = sym in (">",)
        return _classify_lower(value, bound, strict), None

    m = re.match(r"^\s*([\d.,]+)\s*[-–]\s*([\d.,]+)\s*$", r.strip())
    if m:
        lo, hi = _to_float(m.group(1)), _to_float(m.group(2))
        return _classify_interval(value, lo, hi), None

    return "unparsed", "Không parse được tham chiếu"


def compare_extracted_report_on_form(
    text: str,
    *,
    patient_sex: str | None = None,
) -> dict[str, Any]:
    """
    Đọc toàn bộ văn bản extract, tìm các dòng lab đã format, so sánh số học.

    Trả về:
      - ``rows``: mọi chỉ số đã parse
      - ``abnormal``: chỉ các dòng ``status`` là ``high`` hoặc ``low``
      - ``summary``: đếm
      - ``sex_used`` / ``sex_inferred``
    """
    sex = normalize_sex(patient_sex) or infer_sex_from_extract(text)
    sex_inferred = normalize_sex(patient_sex) is None and infer_sex_from_extract(text) is not None

    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parsed = _parse_formatted_line(line)
        if not parsed:
            continue
        val = _parse_float_result(parsed["value_str"])
        if val is None:
            rows.append(
                {
                    **parsed,
                    "value": None,
                    "status": "skipped",
                    "detail": "Kết quả không phải số (định tính hoặc không đọc được)",
                }
            )
            continue
        st, detail = classify_value_against_reference(val, parsed["reference_raw"], sex)
        rows.append(
            {
                **parsed,
                "value": val,
                "status": st,
                "detail": detail,
            }
        )

    abnormal = [r for r in rows if r.get("status") in ("high", "low")]
    n_skip = sum(1 for r in rows if r.get("status") == "skipped")
    n_unparsed = sum(1 for r in rows if r.get("status") == "unparsed")
    n_within = sum(1 for r in rows if r.get("status") == "within")
    return {
        "summary": {
            "n_rows": len(rows),
            "n_within": n_within,
            "n_abnormal": len(abnormal),
            "n_skipped": n_skip,
            "n_unparsed": n_unparsed,
        },
        "sex_used": sex,
        "sex_inferred": sex_inferred,
        "rows": rows,
        "abnormal": abnormal,
    }


def format_on_form_lab_for_llm(data: dict[str, Any] | None, *, language: str = "vi") -> str:
    """
    Văn bản ngắn gọn để chèn vào prompt LLM: chỉ các chỉ số **bất thường** (high/low),
    tránh model liệt kê từng chỉ số bình thường hoặc bịa xét nghiệm không có trên phiếu.
    """
    if not data:
        return ""
    en = language.lower().startswith("en")
    lines: list[str] = [
        "=== PYTHON COMPARISON VS PRINTED REFERENCE (ground truth) ==="
        if en
        else "=== KẾT QUẢ SO SÁNH THEO THAM CHIẾU IN TRÊN PHIẾU (Python, đã kiểm số học) ===",
    ]
    sex = data.get("sex_used")
    if sex:
        inf = " (inferred from report)" if en and data.get("sex_inferred") else (" (suy từ phiếu)" if data.get("sex_inferred") else "")
        lines.append(
            f"Sex for male/female refs: {sex}{inf}"
            if en
            else f"Giới tính dùng cho Nam/Nữ: {sex}{inf}"
        )
    else:
        lines.append(
            "Sex unknown — some male/female-specific rows may be skipped."
            if en
            else "Giới tính dùng cho Nam/Nữ: chưa rõ — một số chỉ số Nam/Nữ có thể bị bỏ qua."
        )
    summ = data.get("summary") or {}
    if en:
        lines.append(
            f"Summary: {summ.get('n_abnormal', 0)} abnormal / {summ.get('n_rows', 0)} numeric rows; "
            f"{summ.get('n_within', 0)} within range; {summ.get('n_skipped', 0)} skipped; "
            f"{summ.get('n_unparsed', 0)} unparsed ref."
        )
    else:
        lines.append(
            f"Tóm tắt: {summ.get('n_abnormal', 0)} bất thường / {summ.get('n_rows', 0)} dòng có số; "
            f"{summ.get('n_within', 0)} trong khoảng; {summ.get('n_skipped', 0)} bỏ qua; {summ.get('n_unparsed', 0)} chưa parse ref."
        )
    ab: list[dict[str, Any]] = list(data.get("abnormal") or [])
    if not ab:
        lines.append("")
        lines.append(
            "No analyte is high/low vs printed reference."
            if en
            else "KHÔNG có chỉ số nào cao/thấp hơn tham chiếu in trên phiếu."
        )
        lines.append(
            "→ Answer briefly: routine follow-up; do not invent tests."
            if en
            else "→ Trả lời: vài câu theo dõi định kỳ; không bịa thêm xét nghiệm."
        )
        return "\n".join(lines)

    lines.append("")
    lines.append(
        "ONLY analyse these analytes in detail (out of range) — do not write a section for others:"
        if en
        else "CHỈ PHÂN TÍCH CHI TIẾT CÁC CHỈ SỐ SAU (ngoài khoảng tham chiếu) — không viết mục cho chỉ số khác:"
    )
    st_hi = "high" if en else "cao"
    st_lo = "low" if en else "thấp"
    for r in ab:
        u = (r.get("unit") or "").strip()
        unit_s = f" {u}" if u else ""
        st = r.get("status")
        st_l = st_hi if st == "high" else st_lo if st == "low" else st
        if en:
            lines.append(
                f"- **{r.get('label', '?')}**: value = {r.get('value')}{unit_s} | "
                f"printed ref: {r.get('reference_raw', '')} | → **{st}** ({st_l} vs reference)"
            )
        else:
            lines.append(
                f"- **{r.get('label', '?')}**: KQ = {r.get('value')}{unit_s} | "
                f"tham chiếu in trên phiếu: {r.get('reference_raw', '')} | "
                f"→ **{st}** ({st_l} hơn tham chiếu)"
            )
    lines.append("")
    if en:
        lines.append(
            "Analytes NOT listed above = within range or not compared — do not write long sections; "
            "optional one line: «Other results within printed reference»."
        )
        lines.append("Do not invent tests (e.g. GFR) unless they appear in the extract below.")
    else:
        lines.append(
            "Các chỉ số KHÔNG nằm trong danh sách trên = trong khoảng tham chiếu hoặc không so được — "
            "KHÔNG lập mục phân tích dài; có thể một câu: «Các chỉ số còn lại trong khoảng tham chiếu»."
        )
        lines.append("KHÔNG bịa thêm xét nghiệm (vd. GFR) nếu không có trong bản trích phiếu bên dưới.")

    within_labels = [
        str(r.get("label", "")).strip()
        for r in (data.get("rows") or [])
        if r.get("status") == "within" and (r.get("label") or "").strip()
    ]
    if within_labels:
        joined = ", ".join(within_labels[:48])
        if en:
            lines.append("")
            lines.append(
                "WITHIN reference (ground truth) — **no** ### subsection, **no** pathophysiology/drugs for these names: "
                + joined
            )
        else:
            lines.append("")
            lines.append(
                "Các chỉ số sau ĐÃ **trong khoảng** tham chiếu in trên phiếu (Python) — "
                "**cấm** viết mục `### Tên chỉ số` với nguyên nhân/xử lý/thuốc; "
                "**cấm** gán bệnh (đái tháo đường, rối loạn đường huyết, v.v.) cho các chỉ số này: "
                + joined
            )
    return "\n".join(lines)
