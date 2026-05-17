"""Retrieval Quality Evaluator - Standard Metrics

Provides comprehensive evaluation for GraphRAG retrieval:
- Precision@K: % retrieved nodes that are relevant
- Recall@K: % relevant nodes that were retrieved
- F1 Score: Harmonic mean of Precision and Recall
- MRR (Mean Reciprocal Rank): Ranking quality
- NDCG: Normalized Discounted Cumulative Gain

Example:
    from eval.retrieval_evaluator import RetrievalEvaluator
    
    evaluator = RetrievalEvaluator()
    result = evaluator.evaluate_single(
        query="sốt cao",
        retrieved_nodes=["SỐT", "PARACETAMOL", "HẠ SỐT"],
        expected_nodes=["SỐT", "SỐT XUẤT HUYẾT"],
        k=5
    )
    print(f"Precision@5: {result.precision_at_k:.2f}")
    print(f"Recall@5: {result.recall_at_k:.2f}")
    print(f"F1@5: {result.f1_at_k:.2f}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import math


@dataclass
class RetrievalMetrics:
    """Metrics for a single query."""
    query: str
    k: int
    
    # Basic counts
    retrieved_count: int
    relevant_count: int
    relevant_retrieved_count: int
    
    # Metrics @K
    precision_at_k: float
    recall_at_k: float
    f1_at_k: float
    
    # Ranking metrics
    reciprocal_rank: float  # 1/rank of first relevant item
    ndcg_at_k: float
    
    # Details
    retrieved_nodes: list[str]
    expected_nodes: list[str]
    relevant_retrieved: list[str]
    missing_relevant: list[str]
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "k": self.k,
            "precision@k": round(self.precision_at_k, 4),
            "recall@k": round(self.recall_at_k, 4),
            "f1@k": round(self.f1_at_k, 4),
            "mrr": round(self.reciprocal_rank, 4),
            "ndcg@k": round(self.ndcg_at_k, 4),
            "retrieved": len(self.retrieved_nodes),
            "relevant": len(self.expected_nodes),
            "relevant_retrieved": len(self.relevant_retrieved),
        }


class RetrievalEvaluator:
    """Evaluate retrieval quality with standard IR metrics."""
    
    def __init__(self, k_values: list[int] = None):
        """
        Args:
            k_values: List of K values for @K metrics (default: [3, 5, 10])
        """
        self.k_values = k_values or [3, 5, 10]
        self.results: list[RetrievalMetrics] = []
    
    def _normalize(self, s: str) -> str:
        """Normalize string for comparison."""
        return s.lower().strip().replace("_", " ").replace("-", " ")
    
    def _is_match(self, retrieved: str, expected: str) -> bool:
        """Check if retrieved matches expected (fuzzy)."""
        r = self._normalize(retrieved)
        e = self._normalize(expected)
        return e in r or r in e or self._similarity(r, e) > 0.8
    
    def _similarity(self, a: str, b: str) -> float:
        """Simple Jaccard similarity for word sets."""
        set_a = set(a.split())
        set_b = set(b.split())
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)
    
    def _calculate_dcg(self, relevance_scores: list[float], k: int) -> float:
        """Calculate DCG from relevance scores."""
        dcg = 0.0
        for i, score in enumerate(relevance_scores[:k], start=1):
            dcg += score / math.log2(i + 1)
        return dcg
    
    def evaluate_single(
        self,
        query: str,
        retrieved_nodes: list[str],
        expected_nodes: list[str],
        k: int = 5,
        node_scores: dict[str, float] | None = None,
    ) -> RetrievalMetrics:
        """Evaluate retrieval for a single query.
        
        Args:
            query: The query string
            retrieved_nodes: List of nodes retrieved by the system
            expected_nodes: Ground truth relevant nodes
            k: Cutoff for @K metrics
            node_scores: Optional relevance scores for each retrieved node (for NDCG)
        
        Returns:
            RetrievalMetrics object with all calculated metrics
        """
        # Truncate to K
        retrieved_k = retrieved_nodes[:k]
        
        # Find relevant retrieved nodes
        relevant_retrieved = []
        for r_node in retrieved_k:
            for e_node in expected_nodes:
                if self._is_match(r_node, e_node):
                    relevant_retrieved.append(r_node)
                    break
        
        # Find missing relevant nodes
        missing_relevant = []
        for e_node in expected_nodes:
            found = any(self._is_match(r_node, e_node) for r_node in retrieved_nodes)
            if not found:
                missing_relevant.append(e_node)
        
        # Basic metrics
        retrieved_count = len(retrieved_k)
        relevant_count = len(expected_nodes)
        relevant_retrieved_count = len(relevant_retrieved)
        
        # Precision@K: % retrieved that are relevant
        precision = relevant_retrieved_count / max(1, retrieved_count)
        
        # Recall@K: % relevant that were retrieved
        recall = relevant_retrieved_count / max(1, relevant_count)
        
        # F1@K
        f1 = 2 * (precision * recall) / max(1e-10, precision + recall)
        
        # MRR (Mean Reciprocal Rank)
        reciprocal_rank = 0.0
        for i, r_node in enumerate(retrieved_nodes, start=1):
            for e_node in expected_nodes:
                if self._is_match(r_node, e_node):
                    reciprocal_rank = 1.0 / i
                    break
            if reciprocal_rank > 0:
                break
        
        # NDCG@K
        # Binary relevance: 1 if relevant, 0 if not
        relevance_scores = []
        for r_node in retrieved_k:
            is_relevant = any(self._is_match(r_node, e_node) for e_node in expected_nodes)
            relevance_scores.append(1.0 if is_relevant else 0.0)
        
        # If we have explicit scores, use them
        if node_scores:
            for i, r_node in enumerate(retrieved_k):
                if r_node in node_scores:
                    relevance_scores[i] = node_scores[r_node]
        
        dcg = self._calculate_dcg(relevance_scores, k)
        
        # Ideal DCG (all relevant items at top)
        ideal_relevances = [1.0] * min(relevant_count, k)
        ideal_relevances += [0.0] * (k - len(ideal_relevances))
        idcg = self._calculate_dcg(ideal_relevances, k)
        
        ndcg = dcg / max(1e-10, idcg)
        
        metrics = RetrievalMetrics(
            query=query,
            k=k,
            retrieved_count=retrieved_count,
            relevant_count=relevant_count,
            relevant_retrieved_count=relevant_retrieved_count,
            precision_at_k=precision,
            recall_at_k=recall,
            f1_at_k=f1,
            reciprocal_rank=reciprocal_rank,
            ndcg_at_k=ndcg,
            retrieved_nodes=retrieved_nodes,
            expected_nodes=expected_nodes,
            relevant_retrieved=relevant_retrieved,
            missing_relevant=missing_relevant,
        )
        
        self.results.append(metrics)
        return metrics
    
    def aggregate_metrics(self) -> dict[str, float]:
        """Calculate mean metrics across all evaluated queries."""
        if not self.results:
            return {}
        
        return {
            "mean_precision@k": sum(r.precision_at_k for r in self.results) / len(self.results),
            "mean_recall@k": sum(r.recall_at_k for r in self.results) / len(self.results),
            "mean_f1@k": sum(r.f1_at_k for r in self.results) / len(self.results),
            "mean_mrr": sum(r.reciprocal_rank for r in self.results) / len(self.results),
            "mean_ndcg@k": sum(r.ndcg_at_k for r in self.results) / len(self.results),
            "num_queries": len(self.results),
        }
    
    def generate_report(self) -> str:
        """Generate a markdown report of evaluation results."""
        agg = self.aggregate_metrics()
        
        lines = [
            "# Retrieval Quality Evaluation Report",
            "",
            "## Aggregate Metrics",
            "",
            f"**Queries Evaluated:** {agg.get('num_queries', 0)}",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Mean Precision@K | {agg.get('mean_precision@k', 0):.3f} |",
            f"| Mean Recall@K | {agg.get('mean_recall@k', 0):.3f} |",
            f"| Mean F1@K | {agg.get('mean_f1@k', 0):.3f} |",
            f"| Mean MRR | {agg.get('mean_mrr', 0):.3f} |",
            f"| Mean NDCG@K | {agg.get('mean_ndcg@k', 0):.3f} |",
            "",
            "## Per-Query Results",
            "",
        ]
        
        for r in self.results:
            lines.extend([
                f"### Query: {r.query[:60]}{'...' if len(r.query) > 60 else ''}",
                "",
                f"- **Precision@{r.k}:** {r.precision_at_k:.3f}",
                f"- **Recall@{r.k}:** {r.recall_at_k:.3f}",
                f"- **F1@{r.k}:** {r.f1_at_k:.3f}",
                f"- **MRR:** {r.reciprocal_rank:.3f}",
                f"- **NDCG@{r.k}:** {r.ndcg_at_k:.3f}",
                "",
                f"**Retrieved ({len(r.retrieved_nodes)}):** {', '.join(r.retrieved_nodes[:10])}{'...' if len(r.retrieved_nodes) > 10 else ''}",
                "",
                f"**Expected ({len(r.expected_nodes)}):** {', '.join(r.expected_nodes)}",
                "",
            ])
            
            if r.missing_relevant:
                lines.extend([
                    f"**Missing Relevant:** {', '.join(r.missing_relevant)}",
                    "",
                ])
            
            lines.append("")
        
        return "\n".join(lines)
