"""Deterministic text chunker producing stable offset-anchored spans."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkSpec:
    seq: int
    start_offset: int
    end_offset: int
    text: str


def chunk_text(
    text: str,
    *,
    target_chars: int = 1200,
    overlap_chars: int = 100,
) -> list[ChunkSpec]:
    """Split `text` into overlapping spans on paragraph boundaries.

    Deterministic: identical input + params always yields identical spans.
    `text[start_offset:end_offset]` equals each chunk's `text`.
    """
    if not text.strip():
        return []

    n = len(text)
    if n <= target_chars:
        return [ChunkSpec(seq=0, start_offset=0, end_offset=n, text=text)]

    specs: list[ChunkSpec] = []
    seq = 0
    start = 0
    while start < n:
        end = min(start + target_chars, n)
        if end < n:
            # Prefer to break on the last paragraph boundary within the window.
            boundary = text.rfind("\n\n", start, end)
            if boundary > start:
                end = boundary
            else:
                space = text.rfind(" ", start, end)
                if space > start:
                    end = space
        specs.append(
            ChunkSpec(seq=seq, start_offset=start, end_offset=end, text=text[start:end])
        )
        seq += 1
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)
    return specs
