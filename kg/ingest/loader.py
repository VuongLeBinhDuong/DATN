from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class RawDocument:
    doc_id: str
    title: str
    source: str
    text: str


def _stable_id(prefix: str, value: str) -> str:
    h = hashlib.sha1(value.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}_{h}"


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_pdf(path: Path) -> str:
    # PyMuPDF is already a dependency in this repo.
    import fitz  # type: ignore

    pieces: list[str] = []
    doc = fitz.open(str(path))
    try:
        for page in doc:
            t = (page.get_text("text") or "").strip()
            if t:
                pieces.append(t)
    finally:
        doc.close()
    return "\n\n".join(pieces).strip()


def load_raw_documents_from_dir(
    root: str | Path,
    *,
    include_globs: Iterable[str] = ("**/*.md", "**/*.txt", "**/*.pdf"),
    max_bytes: int = 25_000_000,
) -> list[RawDocument]:
    base = Path(root)
    docs: list[RawDocument] = []
    for pattern in include_globs:
        for p in base.glob(pattern):
            if not p.is_file():
                continue
            try:
                if p.stat().st_size > max_bytes:
                    continue
            except OSError:
                continue

            rel = str(p.relative_to(base)).replace("\\", "/")
            doc_id = _stable_id("doc", rel)
            title = p.stem
            source = rel

            suffix = p.suffix.lower()
            if suffix == ".pdf":
                text = _read_pdf(p)
            else:
                text = _read_text_file(p)

            text = (text or "").strip()
            if not text:
                continue

            docs.append(RawDocument(doc_id=doc_id, title=title, source=source, text=text))
    # Stable ordering for reproducibility
    docs.sort(key=lambda d: d.source)
    return docs

