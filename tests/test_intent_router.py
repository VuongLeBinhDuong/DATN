"""Tests for core/intent_router.py - Lightweight LLM router & regex fallback tests.
"""

from unittest.mock import MagicMock, patch
import pytest
from core.intent_router import detect_intent


def test_detect_intent_regex_direct_db():
    """Test that regex matches direct_db instantly without invoking LLM."""
    with patch("core.llm_backends.OllamaBackend") as mock_backend:
        res = detect_intent("glucose của tôi là 7.5 mmol/L")
        assert res == "direct_db"
        mock_backend.assert_not_called()


def test_detect_intent_regex_social():
    """Test that obvious pure social matches global_summary instantly without invoking LLM."""
    with patch("core.llm_backends.OllamaBackend") as mock_backend:
        res = detect_intent("xin chào")
        assert res == "global_summary"
        mock_backend.assert_not_called()


def test_detect_intent_llm_fallback():
    """Test that fallback to LLM routes correctly."""
    with patch("core.llm_backends.OllamaBackend") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        mock_instance.is_available.return_value = True
        mock_instance.chat.return_value = "graph_first"
        
        res = detect_intent("bị tiểu đường có dùng được paracetamol không?")
        assert res == "graph_first"
        mock_instance.chat.assert_called_once()
