from __future__ import annotations

import json
import re
from typing import Any


def _strip_code_fences(s: str) -> str:
    t = (s or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    return t.strip()


def extract_first_json(value: str) -> Any:
    """Extract and parse the first JSON object/array found in a string."""
    t = _strip_code_fences(value)
    if not t:
        raise ValueError("empty response")

    # Fast path
    try:
        return json.loads(t)
    except Exception:
        pass

    # Try to locate a JSON array/object substring
    start_candidates = [i for i, ch in enumerate(t) if ch in "[{"]
    for start in start_candidates[:5]:
        for end in range(len(t), start + 1, -1):
            if t[end - 1] not in "]}":
                continue
            snippet = t[start:end]
            try:
                return json.loads(snippet)
            except Exception:
                continue

    raise ValueError("no valid JSON found")

