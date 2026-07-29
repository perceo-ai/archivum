"""Deterministic ingestion stage: content-address → dedup/version → parse →
chunk → persist. Evidence (L0) is immutable; re-ingest creates new versions."""

from __future__ import annotations

from datetime import UTC, datetime

from archivum.config import Settings, get_settings
from archivum.store.blobs import BlobStore
from archivum.store.chunking import chunk_text
from archivum.store.hashing import sha256_bytes, sha256_text
from archivum.store.models import (
    Chunk,
    Document,
    IngestResult,
    Source,
    new_id,
)
from archivum.store.normalize import normalize
from archivum.store.repository import SourceStore
from archivum.store.source_types import SourceType, detect_source_type


async def ingest_source(
    *,
    origin_uri: str,
    raw_bytes: bytes,
    scope: str = "personal",
    explicit_type: SourceType | str | None = None,
    store: SourceStore | None = None,
    blob_store: BlobStore | None = None,
    settings: Settings | None = None,
) -> IngestResult:
    """Ingest one source deterministically. Returns an IngestResult.

    Idempotent per (origin_uri, content_hash): identical re-ingest is a no-op
    that returns the existing rows with deduplicated=True. Changed bytes always
    produce a new version; existing rows and blobs are never mutated.
    """
    s = settings or get_settings()
    store = store or SourceStore()
    blob_store = blob_store or BlobStore(s.blob_dir)

    content_hash = sha256_bytes(raw_bytes)

    # Dedup: if this exact content already exists for this origin, no-op.
    existing_version = await _existing_version(store, origin_uri, content_hash)
    if existing_version is not None:
        existing = await store.get_source_by_hash_and_version(content_hash, existing_version)
        assert existing is not None
        document = await store.get_document_for_source(existing.id)
        assert document is not None
        chunks = await store.list_chunks(document.id)
        return IngestResult(
            source=existing, document=document, chunks=chunks, deduplicated=True
        )

    # New version = one past the highest existing for this origin.
    version = await store.latest_version_for_origin(origin_uri) + 1

    # L0: write raw evidence once (content-addressed).
    blob_store.put(raw_bytes)

    # Normalize (parse) into text + mime.
    normalized = await normalize(origin_uri)
    normalized_hash = sha256_text(normalized.text)

    now = datetime.now(UTC).isoformat()
    source_type = detect_source_type(
        origin_uri=origin_uri, mime=normalized.mime, explicit=explicit_type
    )

    source = Source(
        id=new_id(),
        content_hash=content_hash,
        version=version,
        source_type=source_type,
        origin_uri=origin_uri,
        scope=scope,
        ingested_at=now,
        recorded_at=now,
        valid_from=now,
        valid_to=None,
    )
    await store.insert_source(source)

    document = Document(
        id=new_id(),
        source_id=source.id,
        mime=normalized.mime,
        normalized_hash=normalized_hash,
    )
    await store.insert_document(document)

    chunks: list[Chunk] = []
    for spec in chunk_text(normalized.text):
        chunk = Chunk(
            id=new_id(),
            document_id=document.id,
            seq=spec.seq,
            start_offset=spec.start_offset,
            end_offset=spec.end_offset,
            text_hash=sha256_text(spec.text),
        )
        await store.insert_chunk(chunk)
        chunks.append(chunk)

    return IngestResult(
        source=source, document=document, chunks=chunks, deduplicated=False
    )


async def _existing_version(
    store: SourceStore, origin_uri: str, content_hash: str
) -> int | None:
    """Return the version at which this exact content already exists for the
    origin, or None. Scans existing versions for a content_hash match."""
    latest = await store.latest_version_for_origin(origin_uri)
    for version in range(1, latest + 1):
        match = await store.get_source_by_hash_and_version(content_hash, version)
        if match is not None and match.origin_uri == origin_uri:
            return version
    return None
