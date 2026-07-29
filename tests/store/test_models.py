"""Tests for L1 evidence-lineage models."""

from __future__ import annotations

import dataclasses

from archivum.store.models import (
    Chunk,
    Document,
    ExtractionMethod,
    IngestResult,
    Source,
    new_id,
)
from archivum.store.source_types import SourceType


def test_new_id_is_32_hex():
    i = new_id()
    assert len(i) == 32
    assert all(c in "0123456789abcdef" for c in i)


def test_new_id_is_unique():
    assert new_id() != new_id()


def test_extraction_method_values():
    assert {m.value for m in ExtractionMethod} == {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


def test_source_is_frozen():
    s = Source(
        id="a" * 32,
        content_hash="b" * 64,
        version=1,
        source_type=SourceType.DOCUMENT,
        origin_uri="file:///x.txt",
        scope="personal",
        ingested_at="2026-07-28T00:00:00+00:00",
        recorded_at="2026-07-28T00:00:00+00:00",
        valid_from="2026-07-28T00:00:00+00:00",
        valid_to=None,
    )
    assert s.version == 1
    try:
        s.version = 2  # type: ignore[misc]
        raise AssertionError("Source must be frozen")
    except dataclasses.FrozenInstanceError:
        pass


def test_ingest_result_carries_chunks():
    src = Source(
        id="a" * 32, content_hash="b" * 64, version=1,
        source_type=SourceType.DOCUMENT, origin_uri="file:///x", scope="personal",
        ingested_at="t", recorded_at="t", valid_from="t", valid_to=None,
    )
    doc = Document(id="c" * 32, source_id=src.id, mime="text/plain", normalized_hash="d" * 64)
    chunk = Chunk(id="e" * 32, document_id=doc.id, seq=0, start_offset=0, end_offset=5, text_hash="f" * 64)
    result = IngestResult(source=src, document=doc, chunks=[chunk], deduplicated=False)
    assert result.chunks[0].end_offset == 5
    assert result.deduplicated is False
