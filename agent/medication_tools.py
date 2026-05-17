"""Medication-related tools: drug info/image lookup, simple plan, reminder schedule."""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MedicationIntent:
    needs_drug_info: bool
    needs_plan: bool
    needs_reminders: bool
    drug_name: str | None
    doses_per_day: int | None
    days: int | None


_KW_DRUG_INFO = ("thuốc", "thuoc", "drug", "medicine", "hoạt chất", "hoat chat")
_KW_IMAGE = ("ảnh", "anh", "image", "hình", "hinh")
_KW_PLAN = ("kế hoạch", "ke hoach", "uống thuốc", "uong thuoc", "lịch uống", "lieu dung", "dosing")
_KW_REMIND = ("nhắc", "nhac", "remind", "reminder", "lịch", "schedule")
_COMMON_DRUG_NAMES = {
    "paracetamol",
    "acetaminophen",
    "ibuprofen",
    "amoxicillin",
    "omeprazole",
    "metformin",
    "aspirin",
    "atorvastatin",
    "cetirizine",
    "loratadine",
}
# Từ tiếng Anh thường gặp — không phải tên thuốc (tránh "hello" → drug lookup).
_NOT_DRUG_ENGLISH = {
    "hello",
    "hi",
    "hey",
    "thanks",
    "thank",
    "please",
    "sorry",
    "bye",
    "goodbye",
    "yes",
    "no",
    "ok",
    "okay",
    "help",
    "what",
    "when",
    "where",
    "who",
    "how",
    "why",
}
_STOP_TOKENS = {
    "giúp",
    "toi",
    "tôi",
    "cho",
    "về",
    "ve",
    "và",
    "va",
    "để",
    "de",
    "uống",
    "uong",
    "thuốc",
    "thuoc",
    "drug",
    "medicine",
    "plan",
    "lịch",
    "schedule",
    "có",
    "co",
    "tác",
    "tac",
    "dụng",
    "dung",
    "thông",
    "tin",
    "hình",
    "hinh",
    "ảnh",
    "anh",
    "của",
    "cua",
}


def parse_medication_intent(question: str) -> MedicationIntent:
    q = (question or "").strip()
    low = q.lower()
    asks_info = any(k in low for k in _KW_DRUG_INFO) or any(k in low for k in _KW_IMAGE)
    asks_plan = any(k in low for k in _KW_PLAN)
    asks_remind = any(k in low for k in _KW_REMIND)
    if asks_remind and not asks_plan:
        asks_plan = True

    doses = None
    md = re.search(r"(\d{1,2})\s*(?:lần|lan|times?)", low)
    if md:
        doses = max(1, min(8, int(md.group(1))))

    days = None
    my = re.search(r"(\d{1,3})\s*(?:ngày|ngay|days?)", low)
    if my:
        days = max(1, min(90, int(my.group(1))))

    drug_name = _extract_drug_name(q)
    # Fallback intent: if user gives dosing numbers or an identifiable drug name,
    # treat this as medication-related even without explicit keywords.
    if doses is not None or days is not None:
        asks_plan = True
    if drug_name:
        asks_info = True
    if asks_remind and not asks_plan:
        asks_plan = True

    return MedicationIntent(
        needs_drug_info=asks_info,
        needs_plan=asks_plan,
        needs_reminders=asks_remind,
        drug_name=drug_name,
        doses_per_day=doses,
        days=days,
    )


def _extract_drug_name(question: str) -> str | None:
    q = (question or "").strip()
    if not q:
        return None
    quoted = re.search(r"['\"]([^'\"]{2,80})['\"]", q)
    if quoted:
        return quoted.group(1).strip()
    m = re.search(
        r"(?i)(?:thuốc|drug|medicine)\s+(.+?)(?=\b(?:có|co|tác|tac|dụng|dung|thông|tin|hình|ảnh|của|va|và|and)\b|[\.\,\;\:\?\!]|$)",
        q,
    )
    if m:
        raw = m.group(1).strip(" .,:;!?")
        toks = [
            t
            for t in re.findall(r"[^\W\d_]+|[A-Za-z0-9\-\+]+", raw, flags=re.UNICODE)
            if t.lower() not in _STOP_TOKENS and len(t) > 1
        ]
        if toks:
            return " ".join(toks[:3]).strip()
    # Very common case: user types only drug name (e.g., "paracetamol")
    trimmed = q.strip(" .,:;!?").lower()
    if trimmed in _NOT_DRUG_ENGLISH:
        return None
    if trimmed in _COMMON_DRUG_NAMES:
        return trimmed
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9\-\+ ]{2,40}", q.strip()):
        toks = [t for t in q.strip().split() if t.lower() not in _STOP_TOKENS]
        if 1 <= len(toks) <= 3:
            candidate = " ".join(toks)
            if len(candidate) >= 4 and candidate.lower() not in _NOT_DRUG_ENGLISH:
                return candidate
    return None


def lookup_drug_info_and_images(drug_name: str, timeout: int = 15) -> dict[str, Any]:
    # Kept for backward compatibility; collection-based lookup now happens in
    # extract_drug_info_from_collection_context().
    return {
        "drug_name": (drug_name or "").strip(),
        "summary": "",
        "images": [],
        "sources": [],
        "errors": ["Deprecated: use collection-based context lookup."],
    }


def extract_drug_info_from_collection_context(drug_name: str, graphrag_text: str) -> dict[str, Any]:
    """
    Build drug info strictly from GraphRAG collection output text.
    No local-file or external web lookup.
    """
    name = (drug_name or "").strip()
    text = (graphrag_text or "").strip()
    if not text:
        return {
            "drug_name": name,
            "summary": "",
            "images": [],
            "sources": [],
            "errors": ["GraphRAG context is empty."],
        }
    if "unable to answer" in text.lower():
        return {
            "drug_name": name,
            "summary": "",
            "images": [],
            "sources": [],
            "errors": ["GraphRAG did not retrieve relevant context for this drug."],
        }
    all_urls = _extract_all_urls(text)
    imgs = _extract_image_urls(text)
    sources = [{"title": "GraphRAG retrieved URL", "link": u, "source": "graphrag", "score": None} for u in all_urls[:10]]
    summary = text[:2000] + ("…" if len(text) > 2000 else "")
    errors: list[str] = []
    if not imgs:
        errors.append("Collection context has no direct image URL for this drug.")
    return {"drug_name": name, "summary": summary, "images": imgs, "sources": sources, "errors": errors}


def _extract_image_urls(text: str) -> list[str]:
    urls = _extract_all_urls(text)
    out: list[str] = []
    for u in urls:
        low = u.lower()
        if any(x in low for x in (".jpg", ".jpeg", ".png", ".webp", ".gif", "image", "img")):
            if u not in out:
                out.append(u)
    return out


def _extract_all_urls(text: str) -> list[str]:
    out: list[str] = []
    for u in re.findall(r"https?://[^\s<>\"]+", text or "", flags=re.IGNORECASE):
        if u not in out:
            out.append(u)
    return out


def build_medication_plan(
    drug_name: str,
    *,
    doses_per_day: int = 2,
    days: int = 7,
    wake_time: str = "07:00",
    bed_time: str = "22:00",
) -> list[dict[str, Any]]:
    """Build a simple evenly-spaced daily schedule template (educational only)."""
    doses = max(1, min(8, int(doses_per_day)))
    total_days = max(1, min(90, int(days)))
    start = _parse_hhmm(wake_time, default=(7, 0))
    end = _parse_hhmm(bed_time, default=(22, 0))
    start_min = start[0] * 60 + start[1]
    end_min = end[0] * 60 + end[1]
    if end_min <= start_min:
        end_min = start_min + 14 * 60

    if doses == 1:
        mins = [start_min]
    else:
        span = end_min - start_min
        mins = [start_min + round(i * span / (doses - 1)) for i in range(doses)]

    today = dt.date.today()
    rows: list[dict[str, Any]] = []
    for d in range(total_days):
        day = today + dt.timedelta(days=d)
        for m in mins:
            hh = (m // 60) % 24
            mm = m % 60
            rows.append(
                {
                    "drug": drug_name,
                    "date": day.isoformat(),
                    "time": f"{hh:02d}:{mm:02d}",
                    "note": "Nhắc uống thuốc theo chỉ định điều trị đã có.",
                }
            )
    return rows


def build_reminder_events(plan_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in plan_rows:
        date = str(row.get("date") or "").strip()
        time = str(row.get("time") or "").strip()
        drug = str(row.get("drug") or "Thuốc").strip()
        if not date or not time:
            continue
        out.append(
            {
                "title": f"Nhắc uống {drug}",
                "datetime_local": f"{date}T{time}:00",
                "message": str(row.get("note") or ""),
            }
        )
    return out


def render_medication_context(
    info: dict[str, Any] | None,
    plan_rows: list[dict[str, Any]] | None,
    reminders: list[dict[str, Any]] | None,
) -> str:
    lines: list[str] = []
    if info:
        name = info.get("drug_name") or "N/A"
        lines.append(f"--- Drug info lookup ---\nDrug: {name}")
        summary = (info.get("summary") or "").strip()
        lines.append(summary if summary else "(No summary found)")
        imgs = list(info.get("images") or [])
        if imgs:
            lines.append("Image links:\n" + "\n".join(f"- {u}" for u in imgs))
    if plan_rows:
        lines.append("--- Medication plan template ---")
        preview = plan_rows[:12]
        lines.extend(f"- {r['date']} {r['time']} | {r['drug']}" for r in preview)
        if len(plan_rows) > len(preview):
            lines.append(f"... ({len(plan_rows) - len(preview)} more reminders)")
    if reminders:
        lines.append("--- Reminder events ---")
        lines.extend(f"- {r['datetime_local']} | {r['title']}" for r in reminders[:12])
    return "\n".join(lines).strip()


def _parse_hhmm(value: str, default: tuple[int, int]) -> tuple[int, int]:
    m = re.match(r"^\s*(\d{1,2}):(\d{2})\s*$", value or "")
    if not m:
        return default
    hh = max(0, min(23, int(m.group(1))))
    mm = max(0, min(59, int(m.group(2))))
    return hh, mm
