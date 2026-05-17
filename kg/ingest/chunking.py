from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    chunk_id: str
    text: str
    section_path: str | None
    start_offset: int | None
    end_offset: int | None


def _stable_chunk_id(doc_id: str, section_path: str | None, start: int | None, end: int | None) -> str:
    key = f"{doc_id}|{section_path or ''}|{start or -1}|{end or -1}"
    h = hashlib.sha1(key.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"chunk_{h}"


def _split_markdown_sections(md: str) -> list[tuple[str, int, int]]:
    # Returns list of (section_path, start, end) in character offsets.
    text = md or ""
    # heading lines like "# Title", "## Subtitle"
    headings = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"(?m)^(#{1,6})\s+(.+?)\s*$", text)]
    if not headings:
        return []

    sections: list[tuple[str, int, int]] = []
    stack: list[tuple[int, str]] = []  # (level, title)

    for idx, (hs, he, full) in enumerate(headings):
        level = len(full.split()[0])
        title = full[level:].strip()

        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        section_path = " / ".join([t for _, t in stack if t])

        body_start = he + 1
        body_end = headings[idx + 1][0] if idx + 1 < len(headings) else len(text)
        if body_end <= body_start:
            continue
        sections.append((section_path, body_start, body_end))
    return sections


def chunk_text_structured(
    doc_id: str,
    raw_text: str,
    *,
    is_markdown: bool,
    max_chars: int = 2400,
    overlap_chars: int = 200,
) -> list[TextChunk]:
    t = (raw_text or "").strip()
    if not t:
        return []

    chunks: list[TextChunk] = []

    if is_markdown:
        secs = _split_markdown_sections(t)
    else:
        secs = []

    if not secs:
        secs = [("", 0, len(t))]

    for section_path, s0, e0 in secs:
        section_text = t[s0:e0].strip()
        if not section_text:
            continue

        # sliding window by chars (tokenizer-free; good enough baseline)
        start = s0
        cursor = s0
        while cursor < e0:
            window_end = min(cursor + max_chars, e0)
            piece = t[cursor:window_end].strip()
            if piece:
                cid = _stable_chunk_id(doc_id, section_path or None, cursor, window_end)
                chunks.append(
                    TextChunk(
                        chunk_id=cid,
                        text=piece,
                        section_path=section_path or None,
                        start_offset=cursor,
                        end_offset=window_end,
                    )
                )
            if window_end >= e0:
                break
            cursor = max(cursor + (max_chars - overlap_chars), cursor + 1)

    return chunks

