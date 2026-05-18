"""Tests for evaluation metrics and offline evaluation mode.

Verifies calculation of precision, recall, F1, MRR, NDCG, and offline dummy retriever.
"""

from __future__ import annotations

import pytest

from eval.retrieval_evaluator import RetrievalEvaluator
from eval.retrieval_metrics import RetrievalMetricsCalculator
from eval.eval_custom_kg import dummy_graph_first_retrieve


class TestRetrievalMetricsCalculator:
    """Test cases for RetrievalMetricsCalculator."""

    def test_calculate_metrics_perfect_match(self):
        """Test metrics calculation with perfect match."""
        calculator = RetrievalMetricsCalculator(
            expected_entities=["Paracetamol", "Sốt"],
            expected_types=["Drug", "Symptom"]
        )
        
        retrieved = ["Paracetamol", "Sốt", "Vitamin C"]
        # Keys must match exact casing of retrieved list
        entity_types = {"Paracetamol": "Drug", "Sốt": "Symptom", "Vitamin C": "Drug"}
        entity_aliases = {"Paracetamol": ["acetaminophen"], "Sốt": ["fever"]}
        
        metrics = calculator.calculate_metrics(
            retrieved,
            entity_types=entity_types,
            entity_aliases=entity_aliases,
            k=5
        )
        
        assert metrics["precision"] == 2 / 3
        assert metrics["recall"] == 1.0
        assert metrics["f1"] == 2 * (2/3 * 1.0) / (2/3 + 1.0)
        assert metrics["mrr"] == 1.0  # Paracetamol at rank 1 is a match
        assert metrics["ndcg"] > 0.8
        assert len(metrics["missing"]) == 0

    def test_calculate_metrics_partial_match_with_aliases(self):
        """Test matching entities via their aliases."""
        calculator = RetrievalMetricsCalculator(
            expected_entities=["acetaminophen", "fever"]
        )
        
        retrieved = ["Paracetamol", "Cúm"]
        # Keys must match exact casing of retrieved list
        entity_aliases = {"Paracetamol": ["acetaminophen", "tuan"], "Cúm": []}
        
        metrics = calculator.calculate_metrics(
            retrieved,
            entity_aliases=entity_aliases,
            k=5
        )
        
        assert metrics["relevant_retrieved"] == 1  # Paracetamol matches acetaminophen
        assert metrics["recall"] == 0.5


class TestRetrievalEvaluator:
    """Test cases for RetrievalEvaluator standard reports."""

    def test_evaluator_aggregation(self):
        """Test aggregator averages metrics correctly across runs."""
        evaluator = RetrievalEvaluator()
        
        # Perfect run
        evaluator.evaluate_single(
            query="cough",
            retrieved_nodes=["Cough"],
            expected_nodes=["Cough"],
            k=3
        )
        
        # Zero match run
        evaluator.evaluate_single(
            query="flu",
            retrieved_nodes=["Headache"],
            expected_nodes=["Flu"],
            k=3
        )
        
        agg = evaluator.aggregate_metrics()
        assert agg["mean_precision@k"] == 0.5
        assert agg["mean_recall@k"] == 0.5
        assert agg["mean_mrr"] == 0.5
        assert agg["num_queries"] == 2
        
        report = evaluator.generate_report()
        assert "Mean Precision@K" in report
        assert "Query: cough" in report


class TestOfflineEvaluation:
    """Test cases for Offline evaluation helper."""

    def test_dummy_graph_first_retrieve_matches_keywords(self):
        """Test dummy retriever identifies keywords and returns compliance subgraphs."""
        result = dummy_graph_first_retrieve("cho em hỏi về thuốc paracetamol hạ sốt được không")
        
        entities = result.subgraph["entities"]
        names = [e["canonical_name"] for e in entities]
        
        assert "Paracetamol" in names
        assert "Sốt" in names
        assert len(result.evidence_chunks) == 1
        assert "Mock details" in result.evidence_chunks[0]["text"]
