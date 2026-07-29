"""Tests for the deterministic span-anchored chunker."""

from __future__ import annotations

from archivum.store.chunking import ChunkSpec, chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_is_one_chunk():
    text = "Hello world."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].seq == 0
    assert chunks[0].text == text
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(text)


def test_spans_are_exact_slices_of_source():
    text = "\n\n".join(f"Paragraph number {i} " * 40 for i in range(6))
    chunks = chunk_text(text, target_chars=300, overlap_chars=0)
    assert len(chunks) > 1
    for c in chunks:
        assert text[c.start_offset:c.end_offset] == c.text


def test_seq_is_monotonic_from_zero():
    text = "\n\n".join(f"Block {i} " * 40 for i in range(5))
    chunks = chunk_text(text, target_chars=200, overlap_chars=0)
    assert [c.seq for c in chunks] == list(range(len(chunks)))


def test_is_deterministic():
    text = "\n\n".join(f"Para {i} " * 30 for i in range(4))
    assert chunk_text(text, target_chars=250) == chunk_text(text, target_chars=250)
