"""Repository pattern for data access abstraction.

Separates data operations from business logic.
"""

from __future__ import annotations

from repositories.base import KnowledgeRepository, QueryResult
from repositories.factory import get_knowledge_repository

__all__ = [
    "KnowledgeRepository",
    "QueryResult",
    "get_knowledge_repository",
]
