"""Tests for agent/react/ - ReAct pattern implementation.

Tests ReActAgent, parser, and tools.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.react import ReActAgent, ReActParser, ReActParseResult
from agent.react.tools import set_repository, run_graphrag_tool
from core.llm_backends import LLMBackendError
from repositories.base import QueryResult


class TestReActParser:
    """Test cases for ReAct output parser."""

    def test_parse_final_answer(self):
        """Test parsing Final Answer from LLM output."""
        output = """Thought: The user is asking about flu symptoms.
Final Answer: Các triệu chứng cảm cúm bao gồm: sốt, ho, đau họng, nghẹt mũi, mệt mỏi."""
        
        parser = ReActParser()
        result = parser.parse(output)
        
        assert result.type == "finish"
        assert "Các triệu chứng cảm cúm" in result.content

    def test_parse_action(self):
        """Test parsing Action from LLM output."""
        output = """Thought: I need to search for flu symptoms.
Action: graphrag_query
Action Input: triệu chứng cảm cúm"""
        
        parser = ReActParser()
        result = parser.parse(output)
        
        assert result.type == "action"
        assert result.action_name == "graphrag_query"
        assert "triệu chứng cảm cúm" in result.action_input

    def test_parse_empty_output(self):
        """Test parsing empty output returns error."""
        parser = ReActParser()
        result = parser.parse("")
        
        assert result.type == "error"

    def test_parse_with_markdown_code_block(self):
        """Test parsing output with markdown code blocks."""
        output = """Thought: Need to search.
```
Action: graphrag_query
Action Input: flu symptoms
```"""
        
        parser = ReActParser()
        result = parser.parse(output)
        
        assert result.type == "action"
        assert result.action_name == "graphrag_query"


class TestReActAgent:
    """Test cases for ReActAgent."""

    def test_init_default_values(self):
        """Test default initialization values."""
        mock_llm = MagicMock()
        agent = ReActAgent(llm_backend=mock_llm)
        
        assert agent.llm is mock_llm
        assert agent.max_iterations == 5
        assert agent.parse_retries == 3
        assert agent.parser is not None

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        mock_llm = MagicMock()
        agent = ReActAgent(
            llm_backend=mock_llm,
            max_iterations=10,
            parse_retries=5
        )
        
        assert agent.max_iterations == 10
        assert agent.parse_retries == 5

    def test_run_sync_single_iteration(self):
        """Test synchronous run with single iteration."""
        mock_llm = MagicMock()
        mock_llm.chat.return_value = """Thought: I know the answer.
Final Answer: This is the answer."""
        
        agent = ReActAgent(llm_backend=mock_llm)
        result = agent.run_sync("What is flu?")
        
        assert result["answer"] == "This is the answer."
        assert result["iterations"] == 1
        assert result["errors"] == []

    def test_run_sync_with_action(self):
        """Test synchronous run with tool action."""
        mock_llm = MagicMock()
        mock_llm.chat.side_effect = [
            """Thought: Need to search.
Action: graphrag_query
Action Input: flu symptoms""",
            """Observation: Flu symptoms include fever, cough.
Thought: Now I can answer.
Final Answer: Flu symptoms are fever, cough, sore throat."""
        ]
        
        mock_repo = MagicMock()
        mock_repo.query.return_value = QueryResult(
            text="Flu symptoms include fever, cough.",
            sources=[]
        )
        
        agent = ReActAgent(llm_backend=mock_llm)
        set_repository(mock_repo)
        
        result = agent.run_sync("What are flu symptoms?")
        
        assert "fever, cough" in result["answer"]
        assert result["iterations"] == 2

    def test_run_sync_max_iterations_reached(self):
        """Test that agent stops at max iterations."""
        mock_llm = MagicMock()
        # Always returns action, never final answer
        mock_llm.chat.return_value = """Thought: Need more info.
Action: graphrag_query
Action Input: test"""
        
        mock_repo = MagicMock()
        mock_repo.query.return_value = QueryResult(text="Test", sources=[])
        
        agent = ReActAgent(llm_backend=mock_llm, max_iterations=3)
        set_repository(mock_repo)
        
        result = agent.run_sync("Test question")
        
        # Should stop at max iterations
        assert result["iterations"] <= 3
        assert len(result["errors"]) > 0  # Should have error about max iterations

    def test_run_stream_yields_events(self):
        """Test streaming run yields events."""
        mock_llm = MagicMock()
        
        # Mock streaming chunks
        def mock_stream(messages, **kwargs):
            chunks = [
                "Thought: I know",
                " the answer.\n",
                "Final Answer: Answer here."
            ]
            for chunk in chunks:
                yield chunk
        
        mock_llm.chat_stream = mock_stream
        
        agent = ReActAgent(llm_backend=mock_llm)
        events = list(agent.run_stream("Question?"))
        
        # Should have at least step event and done event
        event_types = [e["event"] for e in events]
        assert "step" in event_types
        assert "done" in event_types


class TestReActTools:
    """Test cases for agent/react/tools.py."""

    def test_run_graphrag_tool_simple(self):
        """Test graphrag tool with simple question."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = QueryResult(
            text="Flu symptoms include fever.",
            sources=[{"title": "Medical Source", "score": 0.9}]
        )
        
        set_repository(mock_repo)
        
        text, sources = run_graphrag_tool("flu symptoms", "What are flu symptoms?")
        
        assert "fever" in text
        assert len(sources) == 1
        mock_repo.query.assert_called_once()

    def test_run_graphrag_tool_merged_query(self):
        """Test graphrag tool merges action input with original question."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = QueryResult(text="Answer", sources=[])
        
        set_repository(mock_repo)
        
        # Different action_input and question
        run_graphrag_tool("treatment", "What is flu and how to treat it?")
        
        # Should call query with merged terms
        call_args = mock_repo.query.call_args
        assert "What is flu and how to treat it?" == call_args[0][0]

    def test_set_repository(self):
        """Test setting custom repository."""
        mock_repo = MagicMock()
        
        set_repository(mock_repo)
        
        # Run a tool to verify it uses the mock
        mock_repo.query.return_value = QueryResult(text="Test", sources=[])
        text, _ = run_graphrag_tool("test", "test")
        
        mock_repo.query.assert_called()


class TestReActParseResult:
    """Test cases for ReActParseResult dataclass."""

    def test_create_finish_result(self):
        """Test creating finish result."""
        result = ReActParseResult(
            type="finish",
            content="Final answer here",
            action_name=None,
            action_input=None
        )
        
        assert result.type == "finish"
        assert result.content == "Final answer here"
        assert result.action_name is None

    def test_create_action_result(self):
        """Test creating action result."""
        result = ReActParseResult(
            type="action",
            content=None,
            action_name="graphrag_query",
            action_input="search query"
        )
        
        assert result.type == "action"
        assert result.action_name == "graphrag_query"
        assert result.action_input == "search query"

    def test_create_error_result(self):
        """Test creating error result."""
        result = ReActParseResult(
            type="error",
            content="Invalid format",
            action_name=None,
            action_input=None,
            error="Parse failed"
        )
        
        assert result.type == "error"
        assert result.error == "Parse failed"
