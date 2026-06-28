"""Tests for comparative evaluation suite (GraphRAG vs. Direct LLM).

Verifies metrics calculation, string normalization, parsing, and execution loop behavior.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import eval.eval_system_comparison as esc


class TestComparativeMetrics:
    """Test suite for metrics calculation in comparative evaluator."""

    def test_normalization(self):
        """Test that _norm normalizes spaces and capitalization correctly."""
        assert esc._norm("   Paracetamol   ") == "paracetamol"
        assert esc._norm("Sốt \n  Xuất\t Huyết") == "sốt xuất huyết"
        assert esc._norm(None) == ""

    def test_node_recall(self):
        """Test entity recall logic."""
        expected = ["Paracetamol", "Sốt"]
        
        # Perfect match
        rec, miss = esc._node_recall(expected, ["Paracetamol", "Sốt xuất huyết"])
        assert rec == 1.0
        assert len(miss) == 0

        # Partial match
        rec, miss = esc._node_recall(expected, ["Paracetamol", "Cúm"])
        assert rec == 0.5
        assert "Sốt" in miss

        # Case insensitive match
        rec, miss = esc._node_recall(expected, ["paracetamol", "sốt"])
        assert rec == 1.0
        assert len(miss) == 0

        # Match using context_entities
        rec, miss = esc._node_recall(expected, ["Cúm"], ["Paracetamol", "sốt"])
        assert rec == 1.0
        assert len(miss) == 0

    def test_edge_recall(self):
        """Test edge recall logic."""
        expected_edges = [
            {"source_contains": "PARACETAMOL", "target_contains": "SOT"},
            {"source_contains": "PARACETAMOL", "target_contains": "GAN"}
        ]
        
        found_edges = {
            ("paracetamol", "sot"),
            ("paracetamol", "dạ dày")
        }

        rec, miss = esc._edge_recall(expected_edges, found_edges)
        assert rec == 0.5
        assert "PARACETAMOL -> GAN" in miss

    def test_parse_related_edges(self):
        """Test parsing related edges from text context."""
        context = (
            "Some headers\n"
            "  • PARACETAMOL —[RELATED]→ SỐT\n"
            "  • METFORMIN —[RELATED]→ ĐÁI THÁO ĐƯỜNG\n"
            "Other text that doesn't match"
        )
        edges = esc._parse_related_edges(context)
        assert ("paracetamol", "sốt") in edges
        assert ("sốt", "paracetamol") in edges
        assert ("metformin", "đái tháo đường") in edges
        assert len(edges) == 4  # 2 edges, bidirectional represented as 4 tuples

    def test_calculate_query_metrics(self):
        """Test fact recall and safety pass rates on answer texts."""
        must_include = ["hạ sốt", "an toàn"]
        forbidden = ["an toàn tuyệt đối", "tự ý tăng liều"]

        # Case 1: Perfect facts, no violations
        ans = "Paracetamol hạ sốt rất tốt và an toàn khi dùng đúng liều lượng."
        metrics = esc._calculate_query_metrics(ans, must_include, forbidden, latency=1.5)
        assert metrics.fact_recall == 1.0
        assert metrics.safety_pass is True
        assert len(metrics.found_facts) == 2
        assert len(metrics.violated_claims) == 0
        assert metrics.latency == 1.5

        # Case 2: Partial facts, with violation
        ans = "Thuốc giúp hạ sốt nhưng cần cẩn trọng khi dùng, và bạn tự ý tăng liều cũng được."
        metrics = esc._calculate_query_metrics(ans, must_include, forbidden, latency=0.8)
        assert metrics.fact_recall == 0.5  # Only has 'hạ sốt', 'an toàn' is missing
        assert "hạ sốt" in metrics.found_facts
        assert "an toàn" in metrics.missing_facts
        assert metrics.safety_pass is False
        assert "tự ý tăng liều" in metrics.violated_claims
        assert "an toàn tuyệt đối" not in metrics.violated_claims


class TestComparativeEvaluatorExecution:
    """Test standard evaluation run in mock/offline mode."""

    def test_offline_run_output_generation(self, tmp_path):
        """Test mock run writes JSON and Markdown outputs properly."""
        dataset_file = tmp_path / "test_set.jsonl"
        report_file = tmp_path / "report.md"
        json_file = tmp_path / "results.json"

        # Create tiny test dataset
        case = {
            "id": "t_001",
            "question": "paracetamol cho bệnh gan",
            "expected_nodes": ["paracetamol", "gan"],
            "expected_edges": [{"source_contains": "PARACETAMOL", "target_contains": "GAN"}],
            "must_include_facts": ["gan"],
            "forbidden_claims": ["an toàn tuyệt đối"],
            "domain": "contraindication",
            "difficulty": "medium"
        }
        dataset_file.write_text(json.dumps(case) + "\n", encoding="utf-8")

        # Run main function in offline mode using mock CLI arguments
        test_args = [
            "eval_system_comparison.py",
            "--dataset", str(dataset_file),
            "--out", str(report_file),
            "--json-out", str(json_file),
            "--offline",
            "--limit", "1",
            "--judge"
        ]

        with patch("sys.argv", test_args):
            # Enforce offline mode in module global
            esc.OFFLINE_MODE = True
            res = esc.main()
            assert res == 0

        # Check outputs
        assert report_file.is_file()
        assert json_file.is_file()

        report_content = report_file.read_text(encoding="utf-8")
        assert "# Comparative Evaluation Report" in report_content
        assert "t_001" in report_content
        assert "Accuracy & Safety" in report_content  # Judge section included

        json_content = json.loads(json_file.read_text(encoding="utf-8"))
        assert len(json_content) == 1
        assert json_content[0]["case_id"] == "t_001"
        assert "graphrag_metrics" in json_content[0]
        assert "direct_metrics" in json_content[0]
        assert "judge_eval" in json_content[0]
