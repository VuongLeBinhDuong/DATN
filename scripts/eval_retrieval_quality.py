#!/usr/bin/env python3
"""Evaluate retrieval quality with standard metrics (Precision/Recall/F1).

Usage:
    python scripts/eval_retrieval_quality.py --dataset eval/graph_eval_set.jsonl --k 5
    python scripts/eval_retrieval_quality.py --dataset eval/graph_eval_set.jsonl --out eval/retrieval_report.md --limit 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.retrieval_evaluator import RetrievalEvaluator
from repositories import get_knowledge_repository
from llm_pipeline.neo4j_graphrag import retrieve_graph_context_with_sources


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL dataset."""
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def extract_nodes_from_context(context: str, sources: list[dict]) -> list[str]:
    """Extract node names from GraphRAG sources (entity titles)."""
    nodes = []
    
    # Only use source titles - these are the actual GraphEntity nodes
    for src in sources:
        title = src.get("title", "").strip()
        if title:
            nodes.append(title)
    
    return list(set(nodes))  # Deduplicate


def evaluate_dataset(dataset_path: Path, k: int = 5, limit: int | None = None) -> RetrievalEvaluator:
    """Run evaluation on dataset."""
    cases = load_jsonl(dataset_path)
    if limit:
        cases = cases[:limit]
    
    evaluator = RetrievalEvaluator(k_values=[k])
    repo = get_knowledge_repository("auto")
    
    print(f"Evaluating {len(cases)} queries (k={k})...")
    print("-" * 60)
    
    for i, case in enumerate(cases, 1):
        question = case.get("question", "")
        expected_nodes = case.get("expected_nodes", [])
        
        if not question or not expected_nodes:
            continue
        
        # Run retrieval
        try:
            result = repo.query(question)
            retrieved_nodes = extract_nodes_from_context(result.text, result.sources)
            
            # Debug: show what we got
            if not retrieved_nodes:
                print(f"  [DEBUG] No nodes extracted from context (len={len(result.text)})")
            else:
                print(f"  [DEBUG] Extracted nodes: {retrieved_nodes}")
                print(f"  [DEBUG] Sources: {[s.get('title', 'N/A') for s in result.sources[:3]]}")
        except Exception as e:
            print(f"  [ERROR] Query {i}: {e}")
            import traceback
            traceback.print_exc()
            retrieved_nodes = []
        
        # Evaluate
        metrics = evaluator.evaluate_single(
            query=question,
            retrieved_nodes=retrieved_nodes,
            expected_nodes=expected_nodes,
            k=k,
        )
        
        # Print progress
        print(f"[{i}/{len(cases)}] {question[:50]}...")
        print(f"  Precision@{k}: {metrics.precision_at_k:.3f}")
        print(f"  Recall@{k}: {metrics.recall_at_k:.3f}")
        print(f"  F1@{k}: {metrics.f1_at_k:.3f}")
        print(f"  Retrieved: {len(retrieved_nodes)}, Expected: {len(expected_nodes)}, Match: {metrics.relevant_retrieved_count}")
        
        if metrics.missing_relevant:
            print(f"  Missing: {', '.join(metrics.missing_relevant[:3])}{'...' if len(metrics.missing_relevant) > 3 else ''}")
        print()
    
    return evaluator


def main():
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality")
    parser.add_argument("--dataset", type=Path, default=Path("eval/graph_eval_set.jsonl"),
                        help="Path to evaluation dataset (JSONL)")
    parser.add_argument("--k", type=int, default=5,
                        help="Cutoff for @K metrics (default: 5)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of queries to evaluate")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output path for markdown report")
    
    args = parser.parse_args()
    
    if not args.dataset.exists():
        print(f"Error: Dataset not found: {args.dataset}")
        sys.exit(1)
    
    # Run evaluation
    evaluator = evaluate_dataset(args.dataset, k=args.k, limit=args.limit)
    
    # Print aggregate
    agg = evaluator.aggregate_metrics()
    print("=" * 60)
    print("AGGREGATE METRICS")
    print("=" * 60)
    print(f"Queries: {agg['num_queries']}")
    print(f"Mean Precision@{args.k}: {agg['mean_precision@k']:.3f}")
    print(f"Mean Recall@{args.k}: {agg['mean_recall@k']:.3f}")
    print(f"Mean F1@{args.k}: {agg['mean_f1@k']:.3f}")
    print(f"Mean MRR: {agg['mean_mrr']:.3f}")
    print(f"Mean NDCG@{args.k}: {agg['mean_ndcg@k']:.3f}")
    
    # Save report
    if args.out:
        report = evaluator.generate_report()
        args.out.write_text(report, encoding="utf-8")
        print(f"\nReport saved to: {args.out}")
    
    # Print interpretation
    print("\n" + "=" * 60)
    print("INTERPRETATION")
    print("=" * 60)
    p = agg['mean_precision@k']
    r = agg['mean_recall@k']
    f1 = agg['mean_f1@k']
    
    if p >= 0.8:
        print("✓ Precision: Excellent (>80% retrieved nodes are relevant)")
    elif p >= 0.6:
        print("~ Precision: Good (60-80% relevant)")
    else:
        print("✗ Precision: Poor (<60% relevant - too much noise)")
    
    if r >= 0.8:
        print("✓ Recall: Excellent (>80% relevant nodes retrieved)")
    elif r >= 0.6:
        print("~ Recall: Good (60-80% coverage)")
    else:
        print("✗ Recall: Poor (<60% coverage - missing important info)")
    
    if f1 >= 0.7:
        print("✓ Overall: Strong F1 score")
    elif f1 >= 0.5:
        print("~ Overall: Moderate F1 score")
    else:
        print("✗ Overall: Weak F1 score - needs improvement")


if __name__ == "__main__":
    main()
