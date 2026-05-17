#!/usr/bin/env python3
"""
Kiem tra graph_eval_set.jsonl co khop Neo4j that hay khong.

Van de: expected_nodes / expected_edges co the "bia" hoac dung tu viet tat khong xuat hien
trong title/description cua :GraphEntity — lam node_recall / edge_recall trong eval bi thap
du pipeline van dung.

Script nay (KHONG goi LLM, KHONG chay graphrag query):
- Voi moi expected_node: co it nhat mot :GraphEntity ma title hoac description (lower)
  chua chuoi da chuan hoa giong heuristic trong eval_graph_rag.
- Voi moi expected_edge: co cap (a)-[:RELATED]-(b) thoa source_contains / target_contains.

Ket qua: bao cao Markdown de ban sua JSONL cho sat du lieu.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from neo4j import GraphDatabase
except ImportError as exc:
    raise SystemExit("Can: pip install neo4j") from exc


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL line {i}: {exc}") from exc
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _neo4j_connect():
    p = REPO_ROOT / "config" / "neo4j.json"
    if not p.is_file():
        raise SystemExit(f"Missing {p}")
    cfg = json.loads(p.read_text(encoding="utf-8"))
    if not cfg.get("enabled") or cfg.get("query_backend") != "neo4j":
        raise SystemExit("config/neo4j.json: can enabled=true va query_backend=neo4j")
    uri = os.getenv("NEO4J_URI") or cfg.get("uri")
    user = os.getenv("NEO4J_USER") or cfg.get("user")
    password = os.getenv("NEO4J_PASSWORD") or cfg.get("password")
    database = os.getenv("NEO4J_DATABASE") or cfg.get("database") or "neo4j"
    if not uri or not user or password is None:
        raise SystemExit("Thieu uri/user/password trong config hoac bien moi truong")
    # Windows localhost handshake
    from urllib.parse import urlparse, urlunparse

    try:
        pr = urlparse(str(uri).strip())
        if pr.scheme and pr.hostname and pr.hostname.lower() == "localhost":
            port = pr.port or 7687
            uri = urlunparse((pr.scheme, f"127.0.0.1:{port}", pr.path or "", "", "", ""))
    except Exception:
        pass
    driver = GraphDatabase.driver(str(uri), auth=(str(user), str(password)))
    return driver, str(database)


def _entity_has_substring(session: Any, needle: str) -> bool:
    nd = _norm(needle)
    if not nd:
        return True
    q = """
    MATCH (n:GraphEntity)
    WHERE toLower(coalesce(n.title, '')) CONTAINS $nd
       OR toLower(coalesce(n.description, '')) CONTAINS $nd
    RETURN true AS ok LIMIT 1
    """
    rec = session.run(q, {"nd": nd}).single()
    return rec is not None and bool(rec["ok"])


def _related_pair_exists(session: Any, sa: str, sb: str) -> bool:
    a = _norm(sa)
    b = _norm(sb)
    if not a or not b:
        return True
    q = """
    MATCH (x:GraphEntity)-[:RELATED]-(y:GraphEntity)
    WHERE (toLower(coalesce(x.title, '')) CONTAINS $a OR toLower(coalesce(x.description, '')) CONTAINS $a)
      AND (toLower(coalesce(y.title, '')) CONTAINS $b OR toLower(coalesce(y.description, '')) CONTAINS $b)
    RETURN true AS ok LIMIT 1
    """
    rec = session.run(q, {"a": a, "b": b}).single()
    return rec is not None and bool(rec["ok"])


def _suggest_titles(session: Any, fragment: str, limit: int = 6) -> list[str]:
    frag = _norm(fragment)
    if len(frag) < 2:
        return []
    q = """
    MATCH (n:GraphEntity)
    WHERE toLower(coalesce(n.title, '')) CONTAINS $frag
    RETURN DISTINCT coalesce(n.title, '') AS t
    LIMIT $lim
    """
    return [str(r["t"]) for r in session.run(q, {"frag": frag, "lim": limit}) if r.get("t")]


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate eval JSONL expected_* against Neo4j GraphEntity/RELATED.")
    ap.add_argument("--dataset", type=Path, default=Path("eval/graph_eval_set.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("eval/graph_eval_dataset_validation.md"))
    ap.add_argument("--limit", type=int, default=0, help="Chi xu ly N dong dau (0=tat ca).")
    ap.add_argument(
        "--suggest",
        action="store_true",
        help="Khi thieu node, goi y vai title GraphEntity chua fragment ngan (co the cham).",
    )
    args = ap.parse_args()

    if not args.dataset.is_file():
        raise SystemExit(f"Not found: {args.dataset}")

    cases = _load_jsonl(args.dataset)
    if args.limit > 0:
        cases = cases[: args.limit]

    driver, database = _neo4j_connect()
    lines: list[str] = [
        "# Graph eval dataset vs Neo4j (validation)",
        "",
        f"- Dataset: `{args.dataset}`",
        f"- Cases checked: **{len(cases)}**",
        "",
        "Neu `expected_node` / `expected_edge` khong ton tai trong DB thi metric `eval_graph_rag.py` **khong phan anh chat luong RAG**, ma phan anh **sai lech nhan thuc** giua JSONL va do thi.",
        "",
        "## Tom tat",
        "",
    ]

    problem_blocks: list[str] = []
    n_cases_any_node_miss = 0
    n_cases_any_edge_miss = 0

    try:
        with driver.session(database=database) as session:
            # Nhanh: co label GraphEntity khong
            lab = session.run(
                "CALL db.labels() YIELD label AS l WHERE l = 'GraphEntity' RETURN l LIMIT 1"
            ).single()
            if lab is None:
                lines.append("- **Canh bao**: khong co label `GraphEntity` — chua import graphrag vao Neo4j.")
                lines.append("")
            for c in cases:
                cid = str(c.get("id") or "")
                exp_nodes = [str(x) for x in (c.get("expected_nodes") or [])]
                exp_edges = [x for x in (c.get("expected_edges") or []) if isinstance(x, dict)]
                node_miss: list[str] = []
                for en in exp_nodes:
                    if not _entity_has_substring(session, en):
                        node_miss.append(en)
                edge_miss: list[str] = []
                for e in exp_edges:
                    s = str(e.get("source_contains") or "")
                    t = str(e.get("target_contains") or "")
                    if s and t and not _related_pair_exists(session, s, t):
                        edge_miss.append(f"{s} ~RELATED~ {t}")

                if node_miss:
                    n_cases_any_node_miss += 1
                if edge_miss:
                    n_cases_any_edge_miss += 1

                if node_miss or edge_miss:
                    parts = [f"### `{cid}`", ""]
                    if node_miss:
                        parts.append("**expected_nodes khong tim thay trong bat ky GraphEntity (title/description):**")
                        for m in node_miss:
                            parts.append(f"- `{m}` (chuoi tim kiem: `{_norm(m)}`)")
                            if args.suggest:
                                sug = _suggest_titles(session, m[:32])
                                if sug:
                                    parts.append("  - goi y title: " + "; ".join(f"`{x[:80]}`" for x in sug))
                                else:
                                    parts.append("  - (khong co goi y title chua fragment ngan)")
                        parts.append("")
                    if edge_miss:
                        parts.append("**expected_edges khong co cap RELATED thoa substring:**")
                        for m in edge_miss:
                            parts.append(f"- {m}")
                        parts.append("")
                    problem_blocks.append("\n".join(parts))

        lines.append(f"- So ca co **it nhat mot expected_node khong co trong DB**: **{n_cases_any_node_miss}** / {len(cases)}")
        lines.append(f"- So ca co **it nhat mot expected_edge khong co trong DB**: **{n_cases_any_edge_miss}** / {len(cases)}")
        lines.append("")
        lines.append("## Chi tiet theo tung ca (node + edge)")
        lines.append("")
        if problem_blocks:
            lines.extend(problem_blocks)
        else:
            lines.append("(Khong phat hien expected_node / expected_edge thieu — voi dieu kien substring + RELATED.)")
            lines.append("")
        lines.append("## Goi y sua JSONL")
        lines.append("")
        lines.append("1. Chay `CALL db.index.fulltext.queryNodes('graphEntityFulltext', 'tu khoa') ...` hoac Neo4j Browse de xem **title that**.")
        lines.append("2. Doi `expected_nodes` thanh **substring that** xuat hien trong `title` (hoac viet tat dung trong DB).")
        lines.append("3. Voi `expected_edges`: kiem tra co canh `RELATED` giua hai entity do khong; neu graph chi noi long leo, **bo edge khoi case** hoac doi thanh cap ton tai.")
        lines.append("4. `must_include_facts` / `forbidden_claims` **khong the** validate bang Neo4j — chinh bang doc cau tra loi LLM hoac prompt.")
        lines.append("")
    finally:
        driver.close()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
