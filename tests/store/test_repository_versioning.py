"""Tests for dedup + version-resolution helpers on SourceStore."""

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


def _src(sid: str, content_hash: str, version: int, origin: str) -> Source:
    return Source(
        id=sid, content_hash=content_hash, version=version,
        source_type=SourceType.DOCUMENT, origin_uri=origin, scope="personal",
        ingested_at="t", recorded_at="t", valid_from="t", valid_to=None,
    )


@pytest.mark.asyncio
async def test_dedup_lookup_by_hash_and_version(store):
    src = _src("s1", "a" * 64, 1, "file:///x")
    await store.insert_source(src)
    assert await store.get_source_by_hash_and_version("a" * 64, 1, wiki_id="default") == src
    assert await store.get_source_by_hash_and_version("a" * 64, 2, wiki_id="default") is None


@pytest.mark.asyncio
async def test_latest_version_for_origin(store):
    assert await store.latest_version_for_origin("file:///x") == 0
    await store.insert_source(_src("s1", "a" * 64, 1, "file:///x"))
    await store.insert_source(_src("s2", "b" * 64, 2, "file:///x"))
    assert await store.latest_version_for_origin("file:///x") == 2


@pytest.mark.asyncio
async def test_document_and_chunks_readback(store):
    src = _src("s1", "a" * 64, 1, "file:///x")
    await store.insert_source(src)
    doc = Document(id="d1", source_id="s1", mime="text/plain", normalized_hash="n" * 64)
    await store.insert_document(doc)
    await store.insert_chunk(Chunk(id="c1", document_id="d1", seq=1, start_offset=5, end_offset=9, text_hash="t" * 64))
    await store.insert_chunk(Chunk(id="c0", document_id="d1", seq=0, start_offset=0, end_offset=4, text_hash="u" * 64))
    assert await store.get_document_for_source("s1") == doc
    chunks = await store.list_chunks("d1")
    assert [c.seq for c in chunks] == [0, 1]
