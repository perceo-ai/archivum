"""Tests for SourceStore CRUD (real in-memory-style DB via temp file)."""

from __future__ import annotations

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.models import Chunk, Document, Source
from archivum.store.repository import SourceStore
from archivum.store.source_types import SourceType


@pytest.fixture
async def store(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db")
    await sqlite_mod.init_db(settings)
    return SourceStore()


def _make_source(**over) -> Source:
    base = dict(
        id="s" * 32, content_hash="h" * 64, version=1,
        source_type=SourceType.DOCUMENT, origin_uri="file:///x.txt",
        scope="personal", ingested_at="t", recorded_at="t",
        valid_from="t", valid_to=None,
    )
    base.update(over)
    return Source(**base)


@pytest.mark.asyncio
async def test_insert_and_get_source(store):
    src = _make_source()
    await store.insert_source(src)
    fetched = await store.get_source(src.id)
    assert fetched == src


@pytest.mark.asyncio
async def test_get_missing_source_returns_none(store):
    assert await store.get_source("nope") is None


@pytest.mark.asyncio
async def test_get_source_by_origin_and_hash(store):
    src = _make_source(origin_uri="file:///a.txt", content_hash="a" * 64)
    await store.insert_source(src)
    # exact (origin, hash) match in one query
    assert await store.get_source_by_origin_and_hash("file:///a.txt", "a" * 64) == src
    # right hash, wrong origin → no match (dedup is origin-scoped)
    assert await store.get_source_by_origin_and_hash("file:///other.txt", "a" * 64) is None
    # unknown → None
    assert await store.get_source_by_origin_and_hash("file:///a.txt", "z" * 64) is None


@pytest.mark.asyncio
async def test_insert_document_and_chunk(store):
    src = _make_source()
    await store.insert_source(src)
    doc = Document(id="d" * 32, source_id=src.id, mime="text/plain", normalized_hash="n" * 64)
    await store.insert_document(doc)
    chunk = Chunk(id="c" * 32, document_id=doc.id, seq=0, start_offset=0, end_offset=4, text_hash="t" * 64)
    await store.insert_chunk(chunk)
    # No exception == rows persisted under FK constraints.
