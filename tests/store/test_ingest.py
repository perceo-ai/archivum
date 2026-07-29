"""Orchestration + invariant tests for ingest_source()."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.ingest import ingest_source
from archivum.store.normalize import NormalizedDoc
from archivum.store.repository import SourceStore


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return settings, SourceStore(), BlobStore(settings.blob_dir)


def _patch_normalize(text: str, mime: str = "text/plain"):
    return patch(
        "archivum.store.ingest.normalize",
        new=AsyncMock(return_value=NormalizedDoc(text=text, mime=mime, metadata={})),
    )


@pytest.mark.asyncio
async def test_ingest_creates_source_document_chunks(env):
    settings, store, blobs = env
    with _patch_normalize("Hello body text."):
        result = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"Hello body text.",
            store=store, blob_store=blobs, settings=settings,
        )
    assert result.source.version == 1
    assert result.deduplicated is False
    assert result.document.mime == "text/plain"
    assert len(result.chunks) >= 1
    # Blob is content-addressed under the raw bytes.
    assert blobs.exists(result.source.content_hash)


@pytest.mark.asyncio
async def test_reingest_identical_bytes_is_deduplicated(env):
    settings, store, blobs = env
    with _patch_normalize("same content"):
        first = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"same content",
            store=store, blob_store=blobs, settings=settings,
        )
    with _patch_normalize("same content"):
        second = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"same content",
            store=store, blob_store=blobs, settings=settings,
        )
    assert second.deduplicated is True
    assert second.source.id == first.source.id
    assert second.source.version == 1
    assert await store.latest_version_for_origin("file:///a.txt") == 1


@pytest.mark.asyncio
async def test_reingest_changed_bytes_creates_new_version(env):
    settings, store, blobs = env
    with _patch_normalize("v1 body"):
        v1 = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"v1 body",
            store=store, blob_store=blobs, settings=settings,
        )
    with _patch_normalize("v2 body changed"):
        v2 = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"v2 body changed",
            store=store, blob_store=blobs, settings=settings,
        )
    assert v1.source.version == 1
    assert v2.source.version == 2
    assert v2.deduplicated is False
    # Old version is still intact and unmutated (immutability).
    old = await store.get_source(v1.source.id)
    assert old == v1.source
    assert blobs.exists(v1.source.content_hash)
    assert blobs.exists(v2.source.content_hash)


@pytest.mark.asyncio
async def test_evidence_blob_is_never_overwritten(env):
    settings, store, blobs = env
    with _patch_normalize("original"):
        r = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"original",
            store=store, blob_store=blobs, settings=settings,
        )
    assert blobs.get(r.source.content_hash) == b"original"


@pytest.mark.asyncio
async def test_identical_bytes_from_two_origins_are_distinct_sources(env):
    # Same file saved at two paths: version lineage is per-origin, so each is a
    # fresh version 1. Must NOT collide on the (origin_uri, version) uniqueness
    # constraint, and must NOT be treated as a dedup of the other origin.
    settings, store, blobs = env
    with _patch_normalize("shared bytes"):
        a = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"shared bytes",
            store=store, blob_store=blobs, settings=settings,
        )
    with _patch_normalize("shared bytes"):
        b = await ingest_source(
            origin_uri="file:///b.txt", raw_bytes=b"shared bytes",
            store=store, blob_store=blobs, settings=settings,
        )
    assert a.deduplicated is False
    assert b.deduplicated is False
    assert a.source.id != b.source.id
    assert a.source.version == 1
    assert b.source.version == 1
    # Same evidence bytes → same content-addressed blob (L0 dedup is fine).
    assert a.source.content_hash == b.source.content_hash
    # Re-ingesting the same bytes at origin A again still dedups within A.
    with _patch_normalize("shared bytes"):
        a2 = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"shared bytes",
            store=store, blob_store=blobs, settings=settings,
        )
    assert a2.deduplicated is True
    assert a2.source.id == a.source.id
    assert await store.latest_version_for_origin("file:///a.txt") == 1
