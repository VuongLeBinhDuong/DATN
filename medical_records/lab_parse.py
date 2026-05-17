"""Heuristic label–value extraction from report text."""

from __future__ import annotations

import re
from typing import Any

# Label : value [unit]
_LABEL_VALUE = re.compile(
    r"(?mi)^[^\d\n:]{1,45}?\s*[:：]\s*([0-9]+(?:[.,][0-9]+)?)\s*([a-zA-Zµ%/^\\.×x*+-]{0,12})?\s*$"
)
# Or a line like "ALT   45   U/L"
_TOKEN_LINE = re.compile(
    r"(?mi)^\s*([A-Za-zÀ-ỹa-zđ\\s\\.]{2,20}?)\s+([0-9]+(?:[.,][0-9]+)?)\s+([a-zA-Zµ%/^.^9/LµL-]{1,15})\s*$"
)


def parse_labeled_values(text: str) -> list[dict[str, Any]]:
    """Returns list of { raw_label, value, unit }."""
    found: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 3:
            continue
        m = _LABEL_VALUE.match(line)
        if m:
            raw_label = line.split(":", 1)[0].split("：", 1)[0].strip()
            val_s = m.group(1).replace(",", ".")
            try:
                val = float(val_s)
            except ValueError:
                continue
            unit = (m.group(2) or "").strip() or None
            key = (raw_label.lower(), val_s)
            if key in seen:
                continue
            seen.add(key)
            found.append({"raw_label": raw_label, "value": val, "unit": unit})
            continue
        m2 = _TOKEN_LINE.match(line)
        if m2:
            raw_label = m2.group(1).strip()
            val_s = m2.group(2).replace(",", ".")
            try:
                val = float(val_s)
            except ValueError:
                continue
            unit = (m2.group(3) or "").strip()
            key = (raw_label.lower(), val_s)
            if key in seen:
                continue
            seen.add(key)
            found.append({"raw_label": raw_label, "value": val, "unit": unit})
    return found


def to_canonical_value(value: float, unit: str | None, entry: dict[str, Any]) -> tuple[float | None, str]:
    """Convert to the entry’s canonical unit when alt_units match."""
    target = entry.get("unit") or ""
    u = (unit or "").strip().lower().replace("μ", "µ")
    tgt = target.strip().lower().replace("μ", "µ")
    if u == tgt or (not unit and not target):
        return value, target
    for alt in entry.get("alt_units", []):
        au = str(alt.get("unit", "")).strip().lower().replace("μ", "µ")
        if u == au:
            scale = float(alt["scale_to_canonical"])
            return value * scale, target
    if entry.get("id") == "glucose_fasting_mmol" and u in ("mg/dl", "mg/dl."):
        return value / 18.0, target
    return None, target
