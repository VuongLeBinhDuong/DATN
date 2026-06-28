"""Tests for agent/react/ - ReAct subagent execution.

Tests ReActParser regex mapping and ReActAgent execution flow.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agent.react.agent import ReActAgent
from agent.react.parser import ReActParser
from agent.react.tools import run_graphrag_tool
from core.llm_backends import LLMBackendError


class TestReActParser:
    """Test cases for the ReAct pattern parser."""

    def test_parse_final_answer(self):
        """Test parsing of a final answer."""
        parser = ReActParser()
        text = "Thought: I now know the answer.\nFinal Answer: The capital of France is Paris."
        
        result = parser.parse(text)
        
        assert result.kind == "finish"
        assert result.answer == "The capital of France is Paris."
        assert result.action is None
        assert result.input_text is None
        assert result.error_message is None

    def test_parse_action(self):
        """Test parsing of a tool execution action."""
        parser = ReActParser()
        text = "Thought: I need to search.\nAction: graphrag_query\nAction Input: flu symptoms"
        
        result = parser.parse(text)
        
        assert result.kind == "action"
        assert result.action == "graphrag_query"
        assert result.input_text == "flu symptoms"
        assert result.answer is None
        assert result.error_message is None

    def test_parse_empty_output(self):
        """Test parsing of empty or invalid output."""
        parser = ReActParser()
        
        result1 = parser.parse("")
        assert result1.kind == "error"
        assert "empty response" in result1.error_message.lower()
        
        result2 = parser.parse("Hello world")
        assert result2.kind == "error"
        assert "missing action" in result2.error_message.lower()

    def test_parse_with_markdown_code_block(self):
        """Test parsing of actions wrapped in markdown backticks."""
        parser = ReActParser()
        text = """Thought: Need to search.
```
Action: graphrag_query
Action Input: flu symptoms
```"""
        result = parser.parse(text)
        
        assert result.kind == "action"
        assert result.action == "graphrag_query"
        assert result.input_text == "flu symptoms\n```"

    def test_parse_conflicting_action_and_answer(self):
        """Test error when both Action and Final Answer are present."""
        parser = ReActParser()
        text = "Action: query\nAction Input: test\nFinal Answer: done"
        
        result = parser.parse(text)
        
        assert result.kind == "error"
        assert "both action and final answer present" in result.error_message.lower()

    def test_parse_bold_markdown_recovery(self):
        """Test that parser recovers from **Action:** bold markdown wrappers."""
        parser = ReActParser()
        text = "**Action:** graphrag_query\n**Action Input:** flu symptoms"
        
        result = parser.parse(text)
        
        assert result.kind == "action"
        assert result.action == "graphrag_query"
        assert result.input_text == "flu symptoms"


class TestReActAgent:
    """Test cases for the ReAct Agent orchestrator."""

    def test_init_default_values(self):
        """Test initialization with default settings."""
        from core.settings import get_settings
        settings = get_settings()
        agent = ReActAgent()
        assert agent.max_iterations == settings.agent.react_max_iter
        assert agent.parse_retries == settings.agent.react_parse_retries
        assert agent.parser is not None

    def test_init_custom_values(self):
        """Test initialization with custom settings."""
        mock_llm = MagicMock()
        agent = ReActAgent(llm_backend=mock_llm, max_iterations=5, parse_retries=3)
        
        assert agent.llm is mock_llm
        assert agent.max_iterations == 5
        assert agent.parse_retries == 3

    def test_run_sync_single_iteration(self):
        """Test sync execution finishes in a single iteration."""
        mock_llm = MagicMock()
        mock_llm.chat_stream.return_value = ["Thought: I know the answer.\nFinal Answer: This is the answer."]
        
        agent = ReActAgent(llm_backend=mock_llm)
        result = agent.run_sync("Hello")
        
        assert "This is the answer." in result["answer"]
        assert len(result["plan"]["steps"]) == 1
        assert result["plan"]["steps"][0]["type"] == "finish"

    def test_run_sync_with_action(self):
        """Test sync execution that calls a tool first."""
        mock_llm = MagicMock()
        # Iteration 1: Calls tool. Iteration 2: Final answer.
        mock_llm.chat_stream.side_effect = [
            ["Thought: Search flu.\nAction: graphrag_query\nAction Input: flu symptoms"],
            ["Thought: Have observations.\nFinal Answer: Flu symptoms include fever, cough."]
        ]
        
        agent = ReActAgent(llm_backend=mock_llm)
        
        with patch("agent.react.agent.run_graphrag_tool") as mock_tool:
            mock_tool.return_value = ("Flu symptoms: fever, cough.", [])
            
            result = agent.run_sync("What are flu symptoms?")
            
            assert "fever, cough" in result["answer"]
            assert len(result["plan"]["steps"]) == 2
            assert result["plan"]["steps"][0]["type"] == "tool"
            assert result["plan"]["steps"][1]["type"] == "finish"
            mock_tool.assert_called_once_with("flu symptoms", "What are flu symptoms?", use_expansion=False)

    def test_run_sync_max_iterations_reached(self):
        """Test ReAct agent gracefully handles when max iterations are exceeded."""
        mock_llm = MagicMock()
        # LLM keeps wanting to call the tool, but we return different inputs to avoid duplicate loop guard
        mock_llm.chat_stream.side_effect = [
            ["Thought: Search flu 1.\nAction: graphrag_query\nAction Input: flu symptoms 1"],
            ["Thought: Search flu 2.\nAction: graphrag_query\nAction Input: flu symptoms 2"],
        ]
        
        agent = ReActAgent(llm_backend=mock_llm, max_iterations=2)
        
        with patch("agent.react.agent.run_graphrag_tool") as mock_tool:
            mock_tool.return_value = ("Observation details", [])
            
            result = agent.run_sync("Query")
            
            assert "dùng hết số bước" in result["answer"]
            assert len(result["plan"]["steps"]) == 2
            assert "exceeded max_iterations" in result["errors"][0]

    def test_run_stream_yields_events(self):
        """Test streaming execution yields appropriate step and reasoning events."""
        mock_llm = MagicMock()
        mock_llm.chat_stream.return_value = ["Thought: I know.\nFinal Answer: Hello!"]
        
        agent = ReActAgent(llm_backend=mock_llm)
        events = list(agent.run_stream("Hi"))
        
        event_types = [e["event"] for e in events]
        assert "step" in event_types
        assert "reasoning_delta" in event_types
        assert "done" in event_types
        
        # Last event must be final result bundle
        done_event = events[-1]
        assert done_event["event"] == "done"
        assert "Hello!" in done_event["answer"]


class TestReActTools:
    """Test cases for the core tools utilized by the ReAct Agent."""

    def test_run_graphrag_tool_simple(self):
        """Test graphrag_query tool executes and retrieves results."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = MagicMock(
            text="Query results.",
            sources=[{"title": "Source 1", "score": 0.8}]
        )
        
        from agent.react.tools import set_repository
        set_repository(mock_repo)
        try:
            obs, hits = run_graphrag_tool("Query details", "Original question")
            
            assert obs == "Query results."
            assert len(hits) == 1
            assert hits[0]["title"] == "Source 1"
        finally:
            set_repository(None)

    def test_run_graphrag_tool_merging_query(self):
        """Test graphrag_query uses original question if action input is empty."""
        mock_repo = MagicMock()
        mock_repo.query.return_value = MagicMock(text="Context.", sources=[])
        
        from agent.react.tools import set_repository
        set_repository(mock_repo)
        try:
            run_graphrag_tool(None, "Original question", use_expansion=False)
            mock_repo.query.assert_called_once_with("Original question")
        finally:
            set_repository(None)

    def test_medical_calculator_tool_bmi(self):
        """Test medical_calculator tool for BMI calculations."""
        from agent.react.tools import run_medical_calculator_tool
        
        # Test valid BMI calculation
        input_data = '{"type": "bmi", "weight": 70, "height": 175}'
        res = run_medical_calculator_tool(input_data)
        assert "BMI: 22.9" in res
        assert "Bình thường" in res

        # Test invalid input
        assert "Error" in run_medical_calculator_tool('{"type": "bmi", "weight": 70}')

    def test_medical_calculator_tool_egfr(self):
        """Test medical_calculator tool for eGFR calculations."""
        from agent.react.tools import run_medical_calculator_tool
        
        # Test valid eGFR calculation for male
        input_data = '{"type": "egfr", "age": 65, "weight": 70, "creatinine": 1.2, "gender": "male"}'
        res = run_medical_calculator_tool(input_data)
        assert "eGFR (Cockcroft-Gault): 60.8" in res
        assert "Giai đoạn 2" in res

        # Test valid eGFR calculation for female
        input_data_female = '{"type": "egfr", "age": 65, "weight": 70, "creatinine": 1.2, "gender": "female"}'
        res_female = run_medical_calculator_tool(input_data_female)
        assert "eGFR (Cockcroft-Gault): 51.6" in res_female
        assert "Giai đoạn 3" in res_female

    def test_drug_interaction_checker_tool(self):
        """Test drug_interaction_checker tool."""
        from agent.react.tools import run_drug_interaction_checker_tool
        
        mock_client_inst = MagicMock()
        mock_client_inst.search_entities_fulltext.side_effect = [
            [{"entity_id": "metformin", "canonical_name": "Metformin", "type": "DRUG"}],
            [{"entity_id": "aspirin", "canonical_name": "Aspirin", "type": "DRUG"}]
        ]
        mock_client_inst.find_paths_between_entities.return_value = {
            "entities": [
                {"entity_id": "metformin", "canonical_name": "Metformin", "type": "DRUG"},
                {"entity_id": "aspirin", "canonical_name": "Aspirin", "type": "DRUG"}
            ],
            "edges": [
                {
                    "subject_entity_id": "metformin",
                    "object_entity_id": "aspirin",
                    "predicate": "INTERACTS_WITH",
                    "confidence": 0.85,
                    "evidence_chunk_id": "chunk_123"
                }
            ]
        }
        mock_client_inst.fetch_chunks_by_ids.return_value = [
            {"chunk_id": "chunk_123", "text": "Metformin should be used with caution when taken with aspirin."}
        ]
        
        with patch("kg.neo4j_client.Neo4jKGClient", return_value=mock_client_inst):
            input_data = '{"drugs": ["metformin", "aspirin"]}'
            res = run_drug_interaction_checker_tool(input_data)
            assert "KẾT QUẢ TRA CỨU TƯƠNG TÁC THUỐC" in res
            assert "Metformin" in res
            assert "Aspirin" in res
            assert "Tương tác với" in res
            assert "Metformin should be used with caution" in res


class TestReActStreamBuffer:
    """Test cases for ReActStreamBuffer stream filtering."""

    def test_buffer_no_final_answer(self):
        from agent.react.stream_buffer import ReActStreamBuffer
        buf = ReActStreamBuffer()
        
        events = buf.feed("Thought: I need to check the patient. ")
        assert all(e["event"] == "reasoning_delta" for e in events)
        
        events_end = buf.finalize()
        assert len(events_end) == 1
        assert events_end[0]["event"] == "reasoning_delta"
        assert "check the patient." in events_end[0]["text"]

    def test_buffer_with_final_answer(self):
        from agent.react.stream_buffer import ReActStreamBuffer
        buf = ReActStreamBuffer()
        
        events1 = buf.feed("Thought: I know the answer now. Final Answer: ")
        event_types = [e["event"] for e in events1]
        assert "reasoning_end" in event_types
        assert "answer_start" in event_types
        assert buf.has_final_answer is True
        
        events2 = buf.feed("The capital of France is Paris.")
        assert len(events2) == 0
        
        events3 = buf.finalize()
        assert len(events3) == 0

