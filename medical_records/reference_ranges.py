"""Load lab reference intervals from JSON."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]  

def default_reference_path() -> Path:
    return _repo_root() / "config" / "lab_reference_ranges.json"


def _norm_label(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def load_reference_config(path: Path | None = None) -> dict[str, Any]:
    p = path or default_reference_path()
    return json.loads(p.read_text(encoding="utf-8"))


def canonical_match(label: str, entry: dict[str, Any]) -> bool:
    nl = _norm_label(label)
    for name in entry.get("names", []):
        if _norm_label(name) in nl or nl in _norm_label(name):
            return True
    return False


def pick_hemoglobin_entry(cfg: dict[str, Any], patient_sex: str | None) -> dict[str, Any] | None:
    sex = (patient_sex or "").lower().strip()
    entries = cfg.get("ranges", [])
    male_e = next((e for e in entries if e.get("id") == "hemoglobin_male"), None)
    female_e = next((e for e in entries if e.get("id") == "hemoglobin_female"), None)
    if sex in ("female", "f", "woman"):
        return female_e
    if sex in ("male", "m", "man"):
        return male_e
    return male_e
