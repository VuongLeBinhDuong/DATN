"""Tests for clinical NER extraction and Neo4j path querying logic in retrieval/graph_first.py
"""

from unittest.mock import MagicMock, patch
import pytest
from retrieval.graph_first import extract_clinical_entities, graph_first_retrieve


def test_extract_clinical_entities_success():
    """Test that extract_clinical_entities correctly parses clinical entities using the mock LLM."""
    with patch("core.llm_backends.OllamaBackend") as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        mock_instance.is_available.return_value = True
        mock_instance.chat.return_value = (
            '[{"name": "tiểu đường", "type": "DISEASE"}, {"name": "Metformin", "type": "DRUG"}]'
        )
        
        entities = extract_clinical_entities("Bị tiểu đường uống Metformin được không?")
        assert len(entities) == 2
        assert entities[0]["name"] == "tiểu đường"
        assert entities[0]["type"] == "DISEASE"
        assert entities[1]["name"] == "Metformin"
        assert entities[1]["type"] == "DRUG"


def test_graph_first_retrieve_with_path_query():
    """Test that graph_first_retrieve uses path query when clinical entities are found."""
    mock_client = MagicMock()
    
    # Mock search_entities_fulltext returning matched entity IDs
    mock_client.search_entities_fulltext.side_effect = lambda name, limit: [
        {"entity_id": f"id_{name.lower()}", "canonical_name": name}
    ]
    
    # Mock find_paths_between_entities returning valid path subgraph
    mock_client.find_paths_between_entities.return_value = {
        "entities": [
            {"entity_id": "id_tiểu đường", "canonical_name": "tiểu đường"},
            {"entity_id": "id_metformin", "canonical_name": "Metformin"}
        ],
        "edges": [
            {
                "subject_entity_id": "id_metformin",
                "object_entity_id": "id_tiểu đường",
                "predicate": "TREATS",
                "confidence": 0.9,
                "evidence_chunk_id": "chunk_1"
            }
        ]
    }
    
    # Mock chunk retrieval
    mock_client.fetch_chunks_by_ids.return_value = [
        {"chunk_id": "chunk_1", "text": "Metformin is used to treat type 2 diabetes.", "mention_confidence": 0.9}
    ]
    mock_client.fetch_chunks_mentioning_entities.return_value = []
    
    # Mock LLM NER call
    with patch("retrieval.graph_first.extract_clinical_entities") as mock_ner:
        mock_ner.return_value = [
            {"name": "tiểu đường", "type": "DISEASE"},
            {"name": "Metformin", "type": "DRUG"}
        ]
        
        res = graph_first_retrieve("Bị tiểu đường uống Metformin được không?", client=mock_client)
        
        # Verify find_paths_between_entities was called instead of expand_subgraph
        mock_client.find_paths_between_entities.assert_called_once_with(
            ["id_tiểu đường", "id_metformin"], max_hops=2
        )
        mock_client.expand_subgraph.assert_not_called()
        
        assert len(res.evidence_chunks) == 1
        assert res.evidence_chunks[0]["chunk_id"] == "chunk_1"
