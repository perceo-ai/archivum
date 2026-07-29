"""Tests for the /api/sources router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from archivum.auth import CurrentUser, require_writer
from archivum.store.models import Chunk, Document, IngestResult, Source
from archivum.store.source_types import SourceType


def _fake_result(deduplicated=False) -> IngestResult:
    src = Source(
        id="s" * 32, content_hash="h" * 64, version=1,
        source_type=SourceType.DOCUMENT, origin_uri="file:///a.txt",
        scope="personal", ingested_at="t", recorded_at="t",
        valid_from="t", valid_to=None,
    )
    doc = Document(id="d" * 32, source_id=src.id, mime="text/plain", normalized_hash="n" * 64)
    chunk = Chunk(id="c" * 32, document_id=doc.id, seq=0, start_offset=0, end_offset=3, text_hash="t" * 64)
    return IngestResult(source=src, document=doc, chunks=[chunk], deduplicated=deduplicated)


@pytest.fixture
def writer_client(app_client):
    from archivum.main import create_app  # app already built by app_client
    app_client.app.dependency_overrides[require_writer] = lambda: CurrentUser(
        username="admin", role="owner", wiki_id="default"
    )
    yield app_client
    app_client.app.dependency_overrides.pop(require_writer, None)


def test_ingest_endpoint_returns_source(writer_client):
    with patch(
        "archivum.api.sources._read_bytes",
        new=AsyncMock(return_value=b"hello"),
    ), patch(
        "archivum.api.sources.ingest_source",
        new=AsyncMock(return_value=_fake_result()),
    ):
        resp = writer_client.post(
            "/api/sources/ingest", json={"origin_uri": "file:///a.txt"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["deduplicated"] is False
    assert body["chunk_count"] == 1


def test_ingest_endpoint_reports_dedup(writer_client):
    with patch(
        "archivum.api.sources._read_bytes",
        new=AsyncMock(return_value=b"hello"),
    ), patch(
        "archivum.api.sources.ingest_source",
        new=AsyncMock(return_value=_fake_result(deduplicated=True)),
    ):
        resp = writer_client.post(
            "/api/sources/ingest", json={"origin_uri": "file:///a.txt"}
        )
    assert resp.json()["deduplicated"] is True


def test_get_source_404(writer_client):
    with patch(
        "archivum.api.sources.SourceStore.get_source",
        new=AsyncMock(return_value=None),
    ):
        resp = writer_client.get("/api/sources/nope")
    assert resp.status_code == 404
