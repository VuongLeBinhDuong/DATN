"""Evaluate Custom KG retrieval quality.

Usage:
    python eval/eval_custom_kg.py --dataset eval/test_queries.jsonl --out eval/report.md
    python eval/eval_custom_kg.py --limit 10  # Quick test with sample queries
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from eval.retrieval_metrics import RetrievalMetricsCalculator
from kg.neo4j_client import Neo4jKGClient

# Lazy import to avoid circular import
graph_first_retrieve = None
def _get_retriever():
    global graph_first_retrieve
    if graph_first_retrieve is None:
        from retrieval.graph_first import graph_first_retrieve as _gf
        graph_first_retrieve = _gf
    return graph_first_retrieve


def load_queries(dataset_path: str | None, limit: int = 0) -> list[dict[str, Any]]:
    """Load test queries from JSONL or use default sample queries."""
    if dataset_path and Path(dataset_path).exists():
        queries = []
        with open(dataset_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    queries.append(json.loads(line))
        if limit > 0:
            queries = queries[:limit]
        return queries
    
    # Default sample queries
    sample_queries = [
        {
            "id": "q_001",
            "question": "tiểu đường tuýp 2",
            "expected_entities": ["tiểu đường", "đái tháo đường", "diabetes"],
            "expected_types": ["Disease"],
        },
        {
            "id": "q_002",
            "question": "paracetamol hạ sốt",
            "expected_entities": ["paracetamol", "sốt"],
            "expected_types": ["Drug", "Symptom"],
        },
        {
            "id": "q_003",
            "question": "metformin điều trị tiểu đường",
            "expected_entities": ["metformin", "tiểu đường", "insulin"],
            "expected_types": ["Drug", "Disease"],
        },
        {
            "id": "q_004",
            "question": "huyết áp cao",
            "expected_entities": ["huyết áp cao", "tăng huyết áp"],
            "expected_types": ["Disease"],
        },
        {
            "id": "q_005",
            "question": "viêm gan B",
            "expected_entities": ["viêm gan", "viêm gan B"],
            "expected_types": ["Disease"],
        },
        {
            "id": "q_006",
            "question": "hen suyễn điều trị",
            "expected_entities": ["hen suyễn", "salbutamol"],
            "expected_types": ["Disease", "Drug"],
        },
        {
            "id": "q_007",
            "question": "sỏi thận",
            "expected_entities": ["sỏi thận", "thận"],
            "expected_types": ["Disease", "Anatomy"],
        },
        {
            "id": "q_008",
            "question": "kháng sinh amoxicillin",
            "expected_entities": ["amoxicillin", "kháng sinh"],
            "expected_types": ["Drug"],
        },
        {
            "id": "q_009",
            "question": "covid-19 vaccine",
            "expected_entities": ["covid-19", "vaccine"],
            "expected_types": ["Disease"],
        },
        {
            "id": "q_010",
            "question": "đau tim nhồi máu cơ tim",
            "expected_entities": ["đau tim", "nhồi máu cơ tim"],
            "expected_types": ["Disease"],
        },
    ]
    if limit > 0:
        sample_queries = sample_queries[:limit]
    return sample_queries


def run_single_eval(
    query_item: dict[str, Any],
    k_values: list[int] = None,
) -> dict[str, Any]:
    """Run evaluation for a single query."""
    question = query_item["question"]
    expected_entities = query_item.get("expected_entities", [])
    expected_types = query_item.get("expected_types", [])
    
    # Run retrieval (lazy import to avoid circular import)
    retriever = _get_retriever()
    result = retriever(question)
    
    # Extract retrieved entities from subgraph (should have proper canonical_name)
    subgraph_entities = result.subgraph.get("entities", [])
    
    # Valid entity types for medical domain
    VALID_TYPES = {"Disease", "Drug", "Symptom", "Anatomy", "Test", "Treatment", "VitalSign"}
    
    retrieved_entities = []
    entity_types = {}
    for entity in subgraph_entities:
        name = entity.get("canonical_name", "")
        entity_type = entity.get("type", "")
        # Strict filter: must have valid type and reasonable length
        if (name and entity_type in VALID_TYPES and 
            2 <= len(name.split()) <= 5 and  # Entity names 2-5 words
            len(name) >= 3 and len(name) <= 100):  # Reasonable char length
            retrieved_entities.append(name)
            entity_types[name.lower()] = entity_type
    
    # Calculate metrics
    calculator = RetrievalMetricsCalculator(expected_entities, expected_types)
    metrics_by_k = {}
    
    for k in (k_values or [5, 10]):
        metrics = calculator.calculate_metrics(retrieved_entities, entity_types=entity_types, k=k)
        metrics_by_k[k] = metrics
    
    return {
        "query_id": query_item.get("id", "unknown"),
        "question": question,
        "retrieved_entities": retrieved_entities,
        "chunks_count": len(result.evidence_chunks),
        "metrics_by_k": metrics_by_k,
    }


def generate_report(results: list[dict[str, Any]]) -> str:
    """Generate markdown report."""
    lines = [
        "# Custom KG Retrieval Evaluation Report",
        "",
        f"**Total Queries:** {len(results)}",
        "",
        "## Aggregate Metrics",
        "",
    ]
    
    # Aggregate by K
    k_values = set()
    for r in results:
        k_values.update(r["metrics_by_k"].keys())
    
    for k in sorted(k_values):
        precisions = [r["metrics_by_k"][k]["precision"] for r in results if k in r["metrics_by_k"]]
        recalls = [r["metrics_by_k"][k]["recall"] for r in results if k in r["metrics_by_k"]]
        f1s = [r["metrics_by_k"][k]["f1"] for r in results if k in r["metrics_by_k"]]
        mrrs = [r["metrics_by_k"][k]["mrr"] for r in results if k in r["metrics_by_k"]]
        
        avg_p = sum(precisions) / len(precisions) if precisions else 0
        avg_r = sum(recalls) / len(recalls) if recalls else 0
        avg_f1 = sum(f1s) / len(f1s) if f1s else 0
        avg_mrr = sum(mrrs) / len(mrrs) if mrrs else 0
        
        lines.extend([
            f"### K={k}",
            "",
            f"- **Precision@K:** {avg_p:.3f}",
            f"- **Recall@K:** {avg_r:.3f}",
            f"- **F1@K:** {avg_f1:.3f}",
            f"- **MRR:** {avg_mrr:.3f}",
            "",
        ])
    
    lines.extend([
        "## Per-Query Results",
        "",
    ])
    
    for r in results:
        lines.extend([
            f"### {r['query_id']}: {r['question']}",
            "",
            f"**Retrieved Entities ({len(r['retrieved_entities'])}):** {', '.join(r['retrieved_entities'][:10])}",
            "",
            f"**Chunks Retrieved:** {r['chunks_count']}",
            "",
        ])
        
        for k, metrics in sorted(r["metrics_by_k"].items()):
            lines.append(f"- K={k}: P={metrics['precision']:.2f} R={metrics['recall']:.2f} F1={metrics['f1']:.2f} MRR={metrics['mrr']:.2f}")
        
        lines.append("")
    
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate Custom KG retrieval")
    ap.add_argument("--dataset", help="Path to JSONL dataset")
    ap.add_argument("--out", default="eval/report.md", help="Output report path")
    ap.add_argument("--limit", type=int, default=0, help="Limit number of queries")
    ap.add_argument("--k", nargs="+", type=int, default=[5, 10], help="K values for metrics")
    args = ap.parse_args()
    
    print("=== Custom KG Retrieval Evaluation ===")
    print()
    
    # Check if Custom KG is available (load config from file)
    try:
        from llm_pipeline.neo4j_graphrag import load_neo4j_config, neo4j_enabled
        neo_cfg = load_neo4j_config()
        if not neo_cfg or not neo4j_enabled(neo_cfg):
            print("✗ Neo4j not configured. Check config/neo4j.json")
            return 1
        
        # Set environment variables so Neo4jKGClient can pick them up
        import os
        os.environ["NEO4J_URI"] = neo_cfg.get("uri", "")
        os.environ["NEO4J_USER"] = neo_cfg.get("user", "")
        os.environ["NEO4J_PASSWORD"] = neo_cfg.get("password", "")
        os.environ["NEO4J_DATABASE"] = neo_cfg.get("database") or "neo4j"
        
        # Test connection with config
        from neo4j import GraphDatabase
        uri = neo_cfg.get("uri")
        user = neo_cfg.get("user")
        password = neo_cfg.get("password")
        database = neo_cfg.get("database") or "neo4j"
        
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session(database=database) as session:
            result = session.run("MATCH (e:Entity) RETURN count(e) AS n").single()
            count = result["n"] if result else 0
            print(f"✓ Custom KG available: {count:,} entities")
        driver.close()
    except Exception as e:
        print(f"✗ Cannot connect to Custom KG: {e}")
        return 1
    
    # Load queries
    queries = load_queries(args.dataset, args.limit)
    print(f"Loaded {len(queries)} queries")
    print()
    
    # Run evaluation
    results = []
    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] Evaluating: {query['question'][:50]}...")
        result = run_single_eval(query, args.k)
        results.append(result)
    
    # Generate report
    report = generate_report(results)
    
    # Write report
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print()
    print(f"✓ Report written to: {out_path}")
    
    # Print summary
    print()
    print("=== Summary ===")
    for k in args.k:
        precisions = [r["metrics_by_k"][k]["precision"] for r in results if k in r["metrics_by_k"]]
        recalls = [r["metrics_by_k"][k]["recall"] for r in results if k in r["metrics_by_k"]]
        f1s = [r["metrics_by_k"][k]["f1"] for r in results if k in r["metrics_by_k"]]
        
        avg_p = sum(precisions) / len(precisions) if precisions else 0
        avg_r = sum(recalls) / len(recalls) if recalls else 0
        avg_f1 = sum(f1s) / len(f1s) if f1s else 0
        
        print(f"K={k}: Precision={avg_p:.3f} Recall={avg_r:.3f} F1={avg_f1:.3f}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
