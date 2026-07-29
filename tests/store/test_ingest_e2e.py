"""End-to-end deterministic ingestion over a real .txt file (no parser mocks)."""

from __future__ import annotations

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.hashing import sha256_text
from archivum.store.ingest import ingest_source
from archivum.store.repository import SourceStore


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return settings, SourceStore(), BlobStore(settings.blob_dir)


@pytest.mark.asyncio
async def test_full_ingest_of_text_file(env, tmp_path):
    settings, store, blobs = env
    doc_path = tmp_path / "notes.txt"
    body = "First paragraph.\n\nSecond paragraph with more words here."
    doc_path.write_text(body, encoding="utf-8")
    origin = str(doc_path)

    result = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )

    # L0: blob content is the exact raw bytes.
    assert blobs.get(result.source.content_hash) == body.encode("utf-8")
    # L1: document mime is plain text; chunks carry text hashes.
    assert result.document.mime == "text/plain"
    assert result.chunks
    for c in result.chunks:
        assert len(c.text_hash) == 64


@pytest.mark.asyncio
async def test_reingest_same_file_is_dedup_no_new_version(env, tmp_path):
    settings, store, blobs = env
    doc_path = tmp_path / "notes.txt"
    doc_path.write_text("stable content", encoding="utf-8")
    origin = str(doc_path)

    first = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )
    second = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )
    assert second.deduplicated is True
    assert second.source.id == first.source.id
    assert await store.latest_version_for_origin(origin) == 1


@pytest.mark.asyncio
async def test_edited_file_creates_v2_without_mutating_v1(env, tmp_path):
    settings, store, blobs = env
    doc_path = tmp_path / "notes.txt"
    doc_path.write_text("original body", encoding="utf-8")
    origin = str(doc_path)

    v1 = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )
    doc_path.write_text("edited body content", encoding="utf-8")
    v2 = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )

    assert (v1.source.version, v2.source.version) == (1, 2)
    # v1 evidence and row are intact (immutability).
    assert await store.get_source(v1.source.id) == v1.source
    assert blobs.get(v1.source.content_hash) == b"original body"
    assert v1.source.content_hash != v2.source.content_hash
