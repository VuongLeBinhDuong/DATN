"""GraphRAG CLI repository (fallback when Neo4j unavailable).
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# repo_root defined locally to avoid rag_milvus dependency
def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]

from repositories.base import KnowledgeRepository, QueryResult

logger = logging.getLogger(__name__)


def _resolve_graphrag_data_dir(graphrag_root: Path) -> Path | None:
    """Find directory containing entities.parquet."""
    for name in ("update_output", "output"):
        d = graphrag_root / name
        if (d / "entities.parquet").is_file():
            return d
    return None


class GraphRAGCLIRepository(KnowledgeRepository):
    """CLI-based GraphRAG repository (no Neo4j required)."""

    def __init__(self) -> None:
        self.root = _repo_root() / "graphrag"
        self.data_dir = _resolve_graphrag_data_dir(self.root)

    def is_ready(self) -> bool:
        """Check if graphrag data exists."""
        return self.data_dir is not None and self.data_dir.is_dir()

    def health_check(self) -> dict[str, Any]:
        """Return health status."""
        if not self.root.is_dir():
            return {"ok": False, "detail": "Missing graphrag/ directory"}
        if self.data_dir is None:
            return {"ok": False, "detail": "Missing entities.parquet in output/update_output"}
        return {"ok": True, "detail": "OK", "data_dir": str(self.data_dir)}

    def query(
        self,
        question: str,
        retrieval_query: str | None = None,
        top_k: int = 10,
    ) -> QueryResult:
        """Execute query via GraphRAG CLI."""
        rq = retrieval_query or question

        if not self.is_ready():
            return QueryResult(
                text="GraphRAG: No index found. Run: python -m graphrag index -r graphrag",
                sources=[],
            )

        cmd = [
            sys.executable,
            "-m", "graphrag",
            "query",
            "-r", str(self.root),
            "-d", str(self.data_dir),
            rq,
        ]

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"

        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                text=False,
                env=env,
            )
            out = (proc.stdout or b"").decode("utf-8", errors="replace")
            err = (proc.stderr or b"").decode("utf-8", errors="replace")

            if proc.returncode == 0:
                text = out.strip() or "(GraphRAG returned empty output)"
                return QueryResult(text=text, sources=[])

            # Try fallback to graphrag.exe
            exe = shutil.which("graphrag")
            if exe:
                proc2 = subprocess.run(
                    [exe, "query", "-r", str(self.root), "-d", str(self.data_dir), rq],
                    check=False,
                    capture_output=True,
                    text=False,
                    env=env,
                )
                if proc2.returncode == 0:
                    out2 = (proc2.stdout or b"").decode("utf-8", errors="replace")
                    text = out2.strip() or "(GraphRAG returned empty output)"
                    return QueryResult(text=text, sources=[])

            return QueryResult(
                text=f"GraphRAG query failed (exit {proc.returncode}):\n{err or out}",
                sources=[],
            )

        except Exception as e:
            logger.exception("GraphRAG CLI error")
            return QueryResult(
                text=f"GraphRAG CLI error: {e}",
                sources=[],
            )
