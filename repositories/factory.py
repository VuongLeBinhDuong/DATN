"""Repository factory for creating appropriate knowledge repository.
"""

from __future__ import annotations

from typing import Any

from core.settings import get_settings
from llm_pipeline.neo4j_graphrag import load_neo4j_config, neo4j_enabled
from repositories.base import KnowledgeRepository
from repositories.neo4j_repo import Neo4jRepository


def get_knowledge_repository(
    backend: str = "auto",
    config: dict[str, Any] | None = None,
) -> KnowledgeRepository:
    """Factory function to create appropriate repository.
    
    Args:
        backend: Which backend to use ('auto', 'neo4j', 'cli')
        config: Optional configuration override
        
    Returns:
        Configured KnowledgeRepository instance
    """
    settings = get_settings()
    
    if backend == "auto":
        # Check Neo4j first (preferred)
        neo_cfg = config or load_neo4j_config()
        if neo4j_enabled(neo_cfg):
            repo = Neo4jRepository(neo_cfg)
            if repo.is_ready():
                return repo
            repo.close()
        # Fall back to CLI-based GraphRAG
        backend = "cli"
    
    if backend == "neo4j":
        neo_cfg = config or load_neo4j_config()
        return Neo4jRepository(neo_cfg)
    
    if backend == "cli":
        # Import here to avoid circular dependency
        from repositories.graphrag_cli_repo import GraphRAGCLIRepository
        return GraphRAGCLIRepository()
    
    raise ValueError(f"Unknown backend: {backend}")


def get_default_repository() -> KnowledgeRepository:
    """Get default repository based on configuration."""
    settings = get_settings()
    
    # Prefer Neo4j if enabled
    neo_cfg = load_neo4j_config()
    if neo4j_enabled(neo_cfg):
        repo = Neo4jRepository(neo_cfg)
        if repo.is_ready():
            return repo
        repo.close()
    
    # Fall back to CLI
    from repositories.graphrag_cli_repo import GraphRAGCLIRepository
    return GraphRAGCLIRepository()
