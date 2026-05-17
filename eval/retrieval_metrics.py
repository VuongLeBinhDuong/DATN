"""Retrieval Metrics Calculator for Custom KG.

Supports synonym matching via canonical_name and aliases.
"""

from __future__ import annotations

import math
from typing import Any


class RetrievalMetricsCalculator:
    """Calculate retrieval metrics with synonym-aware matching."""
    
    def __init__(
        self,
        expected_entities: list[str],
        expected_types: list[str] | None = None,
    ):
        """
        Args:
            expected_entities: List of expected entity names (canonical or aliases)
            expected_types: Optional list of expected entity types
        """
        self.expected = [self._normalize(e) for e in expected_entities]
        self.expected_types = set(self._normalize(t) for t in (expected_types or []))
    
    def _normalize(self, s: str) -> str:
        """Normalize string for comparison."""
        return s.lower().strip().replace("_", " ").replace("-", " ")
    
    def _is_match(self, retrieved: str, entity_aliases: list[str] | None = None) -> bool:
        """Check if retrieved entity matches expected (fuzzy + synonym)."""
        r = self._normalize(retrieved)
        
        # Direct match
        for e in self.expected:
            if e in r or r in e:
                return True
        
        # Match via aliases
        if entity_aliases:
            for alias in entity_aliases:
                a = self._normalize(alias)
                for e in self.expected:
                    if e in a or a in e:
                        return True
        
        # Similarity match
        for e in self.expected:
            if self._similarity(r, e) > 0.8:
                return True
        
        return False
    
    def _similarity(self, a: str, b: str) -> float:
        """Jaccard similarity for word sets."""
        set_a = set(a.split())
        set_b = set(b.split())
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)
    
    def _is_type_match(self, entity_type: str) -> bool:
        """Check if entity type matches expected types."""
        if not self.expected_types:
            return True
        t = self._normalize(entity_type)
        return t in self.expected_types
    
    def calculate_metrics(
        self,
        retrieved_entities: list[str],
        entity_types: dict[str, str] | None = None,
        entity_aliases: dict[str, list[str]] | None = None,
        k: int = 10,
    ) -> dict[str, float]:
        """
        Calculate retrieval metrics.
        
        Args:
            retrieved_entities: List of retrieved entity canonical names
            entity_types: Dict mapping entity name -> type
            entity_aliases: Dict mapping entity name -> list of aliases
            k: Cutoff for @K metrics
            
        Returns:
            Dict with precision, recall, f1, mrr
        """
        retrieved_k = retrieved_entities[:k]
        entity_types = entity_types or {}
        entity_aliases = entity_aliases or {}
        
        # Find relevant retrieved entities
        relevant_retrieved = []
        for r in retrieved_k:
            if self._is_match(r, entity_aliases.get(r, [])):
                # Type check if specified
                if self.expected_types:
                    if self._is_type_match(entity_types.get(r, "")):
                        relevant_retrieved.append(r)
                else:
                    relevant_retrieved.append(r)
        
        # Find missing relevant
        missing = []
        for e in self.expected:
            found = any(
                self._is_match(r, entity_aliases.get(r, [])) 
                for r in retrieved_entities
            )
            if not found:
                missing.append(e)
        
        # Basic counts
        retrieved_count = len(retrieved_k)
        relevant_count = len(self.expected)
        relevant_retrieved_count = len(relevant_retrieved)
        
        # Metrics
        precision = relevant_retrieved_count / max(1, retrieved_count)
        recall = relevant_retrieved_count / max(1, relevant_count)
        f1 = 2 * (precision * recall) / max(1e-10, precision + recall)
        
        # MRR (Mean Reciprocal Rank)
        mrr = 0.0
        for i, r in enumerate(retrieved_entities, start=1):
            if self._is_match(r, entity_aliases.get(r, [])):
                if not self.expected_types or self._is_type_match(entity_types.get(r, "")):
                    mrr = 1.0 / i
                    break
        
        # NDCG@K
        ndcg = self._calculate_ndcg(retrieved_k, entity_aliases, entity_types, k)
        
        return {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "mrr": mrr,
            "ndcg": ndcg,
            "relevant_retrieved": relevant_retrieved_count,
            "retrieved": retrieved_count,
            "relevant": relevant_count,
            "missing": missing,
        }
    
    def _calculate_ndcg(
        self,
        retrieved_k: list[str],
        entity_aliases: dict[str, list[str]],
        entity_types: dict[str, str],
        k: int,
    ) -> float:
        """Calculate NDCG@K."""
        # Binary relevance scores
        relevances = []
        for r in retrieved_k:
            is_rel = self._is_match(r, entity_aliases.get(r, []))
            if is_rel and self.expected_types:
                is_rel = self._is_type_match(entity_types.get(r, ""))
            relevances.append(1.0 if is_rel else 0.0)
        
        # DCG
        dcg = 0.0
        for i, rel in enumerate(relevances, start=1):
            dcg += rel / math.log2(i + 1)
        
        # Ideal DCG
        ideal_relevances = [1.0] * min(len(self.expected), k)
        ideal_relevances += [0.0] * (k - len(ideal_relevances))
        
        idcg = 0.0
        for i, rel in enumerate(ideal_relevances, start=1):
            idcg += rel / math.log2(i + 1)
        
        return dcg / max(1e-10, idcg)


def evaluate_custom_kg_retrieval(
    query: str,
    expected_entities: list[str],
    expected_types: list[str] | None = None,
    k_values: list[int] = None,
) -> dict[str, Any]:
    """Convenience function to evaluate a single query.
    
    Args:
        query: The search query
        expected_entities: Expected entities to find
        expected_types: Expected entity types
        k_values: List of K values to evaluate at
        
    Returns:
        Dict with metrics for each K
    """
    from retrieval.graph_first import graph_first_retrieve
    
    # Run retrieval
    result = graph_first_retrieve(query)
    
    # Extract entities
    retrieved = []
    entity_types = {}
    entity_aliases = {}
    
    for entity in result.subgraph.get("entities", []):
        name = entity.get("canonical_name", "")
        if name:
            retrieved.append(name)
            entity_types[name] = entity.get("type", "")
            entity_aliases[name] = entity.get("aliases", [])
    
    # Calculate metrics
    calculator = RetrievalMetricsCalculator(expected_entities, expected_types)
    k_values = k_values or [5, 10]
    
    metrics_by_k = {}
    for k in k_values:
        metrics = calculator.calculate_metrics(retrieved, entity_types, entity_aliases, k)
        metrics_by_k[k] = metrics
    
    return {
        "query": query,
        "retrieved_entities": retrieved,
        "chunks_count": len(result.evidence_chunks),
        "metrics_by_k": metrics_by_k,
    }
