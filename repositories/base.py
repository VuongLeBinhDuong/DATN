"""Base repository interface for knowledge storage.

Defines contract for all knowledge retrieval implementations:
- Neo4j (GraphRAG)
- Milvus (Vector search)
- GraphRAG CLI (fallback)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class QueryResult:
    """Standardized result from knowledge repository query."""

    text: str
    sources: list[dict[str, Any]]
    score: float | None = None
    metadata: dict[str, Any] | None = None

    def __bool__(self) -> bool:
        return bool(self.text.strip())


class KnowledgeRepository(ABC):
    """Abstract base class for knowledge retrieval.
    
    All implementations (Neo4j, Milvus, GraphRAG CLI) must inherit
    and implement these methods.
    """

    @abstractmethod
    def query(
        self,
        question: str,
        retrieval_query: str | None = None,
        top_k: int = 10,
    ) -> QueryResult:
        """Execute knowledge query and return results.
        
        Args:
            question: Original user question
            retrieval_query: Optional modified query for retrieval
            top_k: Maximum results to return
            
        Returns:
            QueryResult with text and sources
        """
        ...

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if repository is initialized and ready."""
        ...

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return detailed health status."""
        ...

    def close(self) -> None:
        """Release resources. Override if needed."""
        pass

    def __enter__(self) -> KnowledgeRepository:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()
