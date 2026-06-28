#!/usr/bin/env python3
"""Evaluate Graph RAG retrieval quality on Neo4j.

Metrics:
- node_hit_recall: expected node strings found in returned source titles
- edge_hit_recall: expected (source,target) pairs found in parsed RELATED lines
- groundedness: must_include_facts and forbidden_claims checks on answer text
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from llm_pipeline.graphrag_query import run_graphrag_query_with_sources
from llm_pipeline.neo4j_graphrag import load_neo4j_config, retrieve_graph_context_with_sources


@dataclass
class CaseResult:
    case_id: str
    question: str
    domain: str
    node_recall: float
    edge_recall: float
    grounded_pass: bool
    forbidden_pass: bool
    score: float
    notes: list[str]


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
            raise ValueError(f"Invalid JSONL at line {i}: {exc}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"Line {i} must be a JSON object")
        rows.append(obj)
    return rows


def _parse_related_edges(context: str) -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for ln in (context or "").splitlines():
        # Format from neo4j_graphrag.py: "  • {at} —[{w}]→ {bt}"
        if "—[" not in ln or "]→" not in ln:
            continue
        m = re.search(r"•\s*(.*?)\s*—\[[^\]]*\]→\s*(.*)$", ln)
        if not m:
            continue
        a = _norm(m.group(1))
        b = _norm(m.group(2))
        if a and b:
            edges.add((a, b))
            edges.add((b, a))
    return edges


def _node_recall(
    expected_nodes: list[str],
    source_titles: list[str],
    context_entities: list[str] | None = None,
) -> tuple[float, list[str]]:
    if not expected_nodes:
        return 1.0, []
    if context_entities is None:
        context_entities = []
    miss: list[str] = []
    hay = [_norm(x) for x in source_titles if x] + [_norm(x) for x in context_entities if x]
    hit = 0
    for en in expected_nodes:
        needle = _norm(en)
        ok = any(needle in h or h in needle for h in hay)
        if ok:
            hit += 1
        else:
            miss.append(en)
    return hit / max(1, len(expected_nodes)), miss


def _edge_recall(expected_edges: list[dict[str, str]], found_edges: set[tuple[str, str]]) -> tuple[float, list[str]]:
    if not expected_edges:
        return 1.0, []
    miss: list[str] = []
    hit = 0
    for e in expected_edges:
        s = _norm(str(e.get("source_contains") or ""))
        t = _norm(str(e.get("target_contains") or ""))
        if not s or not t:
            continue
        ok = False
        for a, b in found_edges:
            if s in a and t in b:
                ok = True
                break
        if ok:
            hit += 1
        else:
            miss.append(f"{e.get('source_contains')} -> {e.get('target_contains')}")
    denom = max(1, len([x for x in expected_edges if x.get("source_contains") and x.get("target_contains")]))
    return hit / denom, miss


def _grounded_checks(answer: str, must_include_facts: list[str], forbidden_claims: list[str]) -> tuple[bool, bool, list[str]]:
    txt = _norm(answer)
    notes: list[str] = []
    grounded_pass = True
    for f in must_include_facts:
        ff = _norm(f)
        if ff and ff not in txt:
            grounded_pass = False
            notes.append(f"missing_fact: {f}")
    forbidden_pass = True
    for bad in forbidden_claims:
        bb = _norm(bad)
        if bb and bb in txt:
            forbidden_pass = False
            notes.append(f"forbidden_claim: {bad}")
    return grounded_pass, forbidden_pass, notes


def evaluate_cases(cases: list[dict[str, Any]], *, limit: int = 0) -> list[CaseResult]:
    cfg = load_neo4j_config()
    if cfg is None:
        raise RuntimeError("Cannot load config/neo4j.json")

    out: list[CaseResult] = []
    take = cases[:limit] if limit > 0 else cases
    for idx, c in enumerate(take, start=1):
        cid = str(c.get("id") or f"case_{idx}")
        q = str(c.get("question") or "").strip()
        if not q:
            continue
        domain = str(c.get("domain") or "unknown")
        expected_nodes = [str(x) for x in (c.get("expected_nodes") or [])]
        expected_edges = [x for x in (c.get("expected_edges") or []) if isinstance(x, dict)]
        must_include = [str(x) for x in (c.get("must_include_facts") or [])]
        forbidden = [str(x) for x in (c.get("forbidden_claims") or [])]

        answer, hits = run_graphrag_query_with_sources(q)
        context_text, _ = retrieve_graph_context_with_sources(q, cfg)
        found_edges = _parse_related_edges(context_text)
        source_titles = [str(h.get("title") or "") for h in hits if isinstance(h, dict)]

        context_entities = []
        for line in (context_text or "").splitlines():
            line = line.strip()
            if line.startswith("title:"):
                ent_name = line.split("title:", 1)[1].strip()
                if ent_name:
                    context_entities.append(ent_name)

        nr, missing_nodes = _node_recall(expected_nodes, source_titles, context_entities)
        er, missing_edges = _edge_recall(expected_edges, found_edges)
        gp, fp, gf_notes = _grounded_checks(answer, must_include, forbidden)

        score = 0.4 * nr + 0.3 * er + 0.2 * (1.0 if gp else 0.0) + 0.1 * (1.0 if fp else 0.0)
        notes = []
        notes.extend([f"missing_node: {x}" for x in missing_nodes])
        notes.extend([f"missing_edge: {x}" for x in missing_edges])
        notes.extend(gf_notes)
        out.append(
            CaseResult(
                case_id=cid,
                question=q,
                domain=domain,
                node_recall=nr,
                edge_recall=er,
                grounded_pass=gp,
                forbidden_pass=fp,
                score=score,
                notes=notes,
            )
        )
    return out


def _pct(v: float) -> str:
    return f"{v*100:.1f}%"


def _make_report(results: list[CaseResult], dataset_path: Path) -> str:
    if not results:
        return "# Graph RAG Eval Report\n\nNo results.\n"

    node_avg = statistics.mean(x.node_recall for x in results)
    edge_avg = statistics.mean(x.edge_recall for x in results)
    grounded_rate = statistics.mean(1.0 if x.grounded_pass else 0.0 for x in results)
    forbidden_rate = statistics.mean(1.0 if x.forbidden_pass else 0.0 for x in results)
    score_avg = statistics.mean(x.score for x in results)

    worst = sorted(results, key=lambda x: x.score)[:8]
    lines = [
        "# Graph RAG Eval Report",
        "",
        f"- Dataset: `{dataset_path}`",
        f"- Cases: **{len(results)}**",
        "",
        "## Summary",
        "",
        f"- Node hit recall (avg): **{_pct(node_avg)}**",
        f"- Edge hit recall (avg): **{_pct(edge_avg)}**",
        f"- Grounded pass rate: **{_pct(grounded_rate)}**",
        f"- Forbidden-claim clean rate: **{_pct(forbidden_rate)}**",
        f"- Composite score (avg): **{score_avg:.3f}**",
        "",
        "## Worst Cases",
        "",
        "| id | domain | node | edge | grounded | forbidden | score |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for w in worst:
        lines.append(
            f"| `{w.case_id}` | {w.domain} | {w.node_recall:.2f} | {w.edge_recall:.2f} | "
            f"{'1' if w.grounded_pass else '0'} | {'1' if w.forbidden_pass else '0'} | {w.score:.3f} |"
        )

    lines.append("")
    lines.append("## Detailed Notes")
    lines.append("")
    for r in sorted(results, key=lambda x: x.score):
        if not r.notes:
            continue
        lines.append(f"- `{r.case_id}` ({r.domain}): " + "; ".join(r.notes))

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate Graph RAG retrieval and grounding quality.")
    ap.add_argument("--dataset", type=Path, default=Path("eval/graph_eval_set.jsonl"))
    ap.add_argument("--out", type=Path, default=Path("eval/graph_eval_report.md"))
    ap.add_argument("--limit", type=int, default=0, help="Run first N cases (0=all).")
    args = ap.parse_args()

    if not args.dataset.is_file():
        raise SystemExit(f"Dataset not found: {args.dataset}")

    cases = _load_jsonl(args.dataset)
    results = evaluate_cases(cases, limit=max(0, args.limit))

    report = _make_report(results, args.dataset)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Wrote report: {args.out}")
    print(f"Cases: {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
