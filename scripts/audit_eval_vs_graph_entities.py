#!/usr/bin/env python3
"""Kiem tra expected_nodes / expected_edges trong eval co khop entity title trong Neo4j hay khong.

Neu khong ket noi duoc Neo4j, dung file export JSON (vd. backups/.../neo4j_export/graphentity.json).

Vi du:
  python scripts/audit_eval_vs_graph_entities.py \\
    --entities-json backups/pre_reindex_20260408_210120/neo4j_export/graphentity.json

  python scripts/audit_eval_vs_graph_entities.py --neo4j
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().upper())


def _load_titles_from_json(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("JSON phai la mang object GraphEntity")
    titles: list[str] = []
    for row in data:
        if isinstance(row, dict) and row.get("title"):
            titles.append(str(row["title"]).strip())
    return titles


def _load_titles_from_neo4j() -> list[str]:
    from llm_pipeline.neo4j_graphrag import GraphDatabase, load_neo4j_config, neo4j_enabled

    cfg = load_neo4j_config()
    if not cfg or not neo4j_enabled(cfg):
        raise RuntimeError("config/neo4j.json khong bat hoac thieu")
    if GraphDatabase is None:
        raise RuntimeError("Chua cai neo4j driver")
    import os

    uri = os.getenv("NEO4J_URI") or cfg.get("uri")
    user = os.getenv("NEO4J_USER") or cfg.get("user")
    password = os.getenv("NEO4J_PASSWORD") or cfg.get("password")
    database = os.getenv("NEO4J_DATABASE") or cfg.get("database") or "neo4j"
    if not uri or not user or password is None:
        raise RuntimeError("Thieu uri/user/password Neo4j")
    driver = GraphDatabase.driver(str(uri), auth=(str(user), str(password)))
    titles: list[str] = []
    try:
        with driver.session(database=str(database)) as session:
            for rec in session.run("MATCH (n:GraphEntity) RETURN n.title AS t"):
                t = rec.get("t")
                if t:
                    titles.append(str(t).strip())
    finally:
        driver.close()
    return titles


def _match_expected_to_title(expected: str, titles_norm: dict[str, str]) -> str | None:
    """Tra ve title goc neu tim thay; None neu khong."""
    e = _norm(expected)
    if not e:
        return None
    for orig, n in titles_norm.items():
        if e == n or e in n or n in e:
            return orig
    return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit eval expected_* against GraphEntity titles.")
    ap.add_argument("--dataset", type=Path, default=Path("eval/graph_eval_set.jsonl"))
    ap.add_argument(
        "--entities-json",
        type=Path,
        default=None,
        help="File graphentity.json tu export Neo4j (khuyen dung neu khong muon ket noi DB).",
    )
    ap.add_argument(
        "--neo4j",
        action="store_true",
        help="Lay title truc tiep tu Neo4j (can config/neo4j.json + DB chay).",
    )
    args = ap.parse_args()

    if args.neo4j:
        titles = _load_titles_from_neo4j()
    elif args.entities_json and args.entities_json.is_file():
        titles = _load_titles_from_json(args.entities_json)
    else:
        print(
            "Can --entities-json <path/to/graphentity.json> hoac --neo4j.\n"
            "Vi du: python scripts/audit_eval_vs_graph_entities.py "
            "--entities-json backups/pre_reindex_20260408_210120/neo4j_export/graphentity.json",
            file=sys.stderr,
        )
        return 2

    cases = _load_jsonl(args.dataset)
    missing_all: list[tuple[str, str]] = []
    uniq = len({_norm(t) for t in titles})
    print(f"# Titles trong graph: {len(titles)} (unique norm: {uniq})")
    print(f"# Cases: {len(cases)}\n")

    for c in cases:
        cid = str(c.get("id") or "")
        exp_nodes = [str(x) for x in (c.get("expected_nodes") or [])]
        if not exp_nodes:
            continue
        line_parts = [f"`{cid}`"]
        for en in exp_nodes:
            hit = _match_expected_to_title(en, titles)
            if hit is None:
                missing_all.append((cid, en))
                line_parts.append(f"MISS `{en}`")
            else:
                if _norm(hit) != _norm(en):
                    line_parts.append(f"OK `{en}` -> `{hit}`")
                else:
                    line_parts.append(f"ok `{en}`")
        if any("MISS" in p for p in line_parts):
            print("- " + " | ".join(line_parts))

    print("\n## Tom tat expected_nodes khong khop title nao trong graph")
    if not missing_all:
        print("(khong co — hoac cac case khong expected_nodes)")
    else:
        for cid, en in missing_all:
            print(f"- `{cid}`: `{en}`")

    print(
        "\n*Goi y:* sua `expected_nodes` thanh dung title trong Neo4j (vd. AMLODIPIN thay AMLODIPINE), "
        "hoac them alias trong script eval sau nay."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

```

</think>
<think>
I made a mistake - I added `if __future__.annotations: pass` at the bottom which is wrong - `from __future__ import annotations` is at top. Remove the erroneous block at the end.

Also `_match_expected_to_title` uses `titles_norm: dict[str, str]` but I'm passing `by_norm` which maps norm -> orig. The function iterates `for orig, n in titles_norm.items()` - wrong, should be for n, orig in by_norm.items() or fix the function.

Let me fix the matching logic:

```python
def _match_expected_to_title(expected: str, norm_to_orig: dict[str, str]) -> str | None:
    e = _norm(expected)
    if not e:
        return None
    if e in norm_to_orig:
        return norm_to_orig[e]
    for n, orig in norm_to_orig.items():
        if e in n or n in e:
            return orig
    return None
```

Actually we need all titles not just unique norm - for "e in n" we need to iterate all normalized titles.

```python
def _match_expected_to_title(expected: str, titles: list[str]) -> str | None:
    e = _norm(expected)
    if not e:
        return None
    for orig in titles:
        n = _norm(orig)
        if e == n or e in n or n in e:
            return orig
    return None
```

Simpler - pass titles list.

Also remove the bad `if __future__` block at end.

Fix the script completely.
</think>


<｜tool▁calls▁begin｜><｜tool▁call▁begin｜>
StrReplace