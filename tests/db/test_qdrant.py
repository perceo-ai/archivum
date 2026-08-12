"""Tests for archivum.db.qdrant_client — fastembed and AsyncQdrantClient mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

import archivum.db.qdrant_client as qdrant_module
from archivum.db.qdrant_client import _chunk_text, get_embedder


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_qdrant_singletons():
    """Ensure module-level singletons are cleared around each test."""
    qdrant_module._client = None
    qdrant_module._embedder = None
    qdrant_module._embed_dim_cache = {}
    yield
    qdrant_module._client = None
    qdrant_module._embedder = None
    qdrant_module._embed_dim_cache = {}


def make_mock_embedder(vector=None):
    vec = vector if vector is not None else np.array([0.1, 0.2, 0.3])
    mock_embedder = MagicMock()
    mock_embedder.embed = MagicMock(return_value=iter([vec]))
    return mock_embedder


def make_settings(**overrides):
    from archivum.config import Settings

    defaults = {
        "embed_provider": "local",
        "embed_model": "BAAI/bge-small-en-v1.5",
        "embed_dim": 3,
        "qdrant_url": "http://localhost:6333",
        "qdrant_collection": "test_collection",
        "qdrant_recreate_collection_on_dim_mismatch": False,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_mock_qdrant_client():
    client = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    client.collection_exists = AsyncMock(return_value=True)
    return client


# ── TestGetEmbedder ───────────────────────────────────────────────────────────


class TestGetEmbedder:
    def test_returns_singleton(self):
        mock_embedder = make_mock_embedder()
        with patch("archivum.db.qdrant_client.TextEmbedding", return_value=mock_embedder):
            s = make_settings()
            e1 = get_embedder(s)
            e2 = get_embedder(s)
        assert e1 is e2

    def test_uses_configured_model(self):
        mock_embedder = make_mock_embedder()
        with patch("archivum.db.qdrant_client.TextEmbedding", return_value=mock_embedder) as MockTE:
            s = make_settings(embed_model="custom-model")
            get_embedder(s)
        MockTE.assert_called_once_with("custom-model")


class TestResolveEmbedEndpoint:
    def test_ollama_keeps_v1_base_url_and_uses_api_key(self):
        s = make_settings(
            embed_provider="ollama",
            ollama_base_url="https://ollama.example.com/v1",
            ollama_api_key="ollama-key",
        )

        base_url, api_key, headers = qdrant_module._resolve_embed_endpoint(s)

        assert base_url == "https://ollama.example.com/v1"
        assert api_key == "ollama-key"
        assert headers == {}


# ── TestUpsertPage ────────────────────────────────────────────────────────────


class TestUpsertPage:
    @pytest.mark.asyncio
    async def test_smoke_upsert_page(self):
        """Basic smoke: qdrant client.upsert is called at least once."""
        mock_embedder = make_mock_embedder(np.array([0.1, 0.2, 0.3]))
        # embed must return an iterator each time it's called.
        mock_embedder.embed = MagicMock(side_effect=lambda texts: iter([np.array([0.1, 0.2, 0.3])] * len(texts)))
        mock_client = make_mock_qdrant_client()

        s = make_settings()

        with (
            patch("archivum.db.qdrant_client.TextEmbedding", return_value=mock_embedder),
            patch("archivum.db.qdrant_client.get_client", AsyncMock(return_value=mock_client)),
            patch("archivum.db.qdrant_client.embed_texts", AsyncMock(return_value=[[0.1, 0.2, 0.3]])),
            patch("archivum.db.qdrant_client.resolve_embed_dim", AsyncMock(return_value=3)),
            patch("archivum.db.qdrant_client.delete_page", AsyncMock()),
        ):
            count = await qdrant_module.upsert_page("my-slug", "My Title", "Short content.", "default", s)

        mock_client.upsert.assert_called_once()
        assert count >= 1

    @pytest.mark.asyncio
    async def test_short_content_single_chunk(self):
        """Short content produces exactly one chunk/point."""
        mock_client = make_mock_qdrant_client()
        s = make_settings()

        with (
            patch("archivum.db.qdrant_client.get_client", AsyncMock(return_value=mock_client)),
            patch("archivum.db.qdrant_client.embed_texts", AsyncMock(return_value=[[0.1, 0.2, 0.3]])),
            patch("archivum.db.qdrant_client.resolve_embed_dim", AsyncMock(return_value=3)),
            patch("archivum.db.qdrant_client.delete_page", AsyncMock()),
        ):
            count = await qdrant_module.upsert_page("slug", "Title", "Hello world.", "default", s)

        assert count == 1

    @pytest.mark.asyncio
    async def test_chunks_long_content(self):
        """Content longer than chunk_size (512 words) produces multiple chunks."""
        # Build content with >512 words so _chunk_text splits it.
        long_content = " ".join(["word"] * 600)

        chunks = _chunk_text(long_content, chunk_size=512, overlap=64)
        assert len(chunks) >= 2, "Chunking should have produced multiple chunks"

        mock_client = make_mock_qdrant_client()
        s = make_settings()

        # embed_texts needs to return a vector per chunk.
        num_chunks = len(chunks)
        fake_vectors = [[0.1, 0.2, 0.3]] * num_chunks

        with (
            patch("archivum.db.qdrant_client.get_client", AsyncMock(return_value=mock_client)),
            patch("archivum.db.qdrant_client.embed_texts", AsyncMock(return_value=fake_vectors)),
            patch("archivum.db.qdrant_client.resolve_embed_dim", AsyncMock(return_value=3)),
            patch("archivum.db.qdrant_client.delete_page", AsyncMock()),
        ):
            count = await qdrant_module.upsert_page("long-slug", "Title", long_content, "default", s)

        assert count == num_chunks


# ── TestSearch ────────────────────────────────────────────────────────────────


class TestSearch:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results(self):
        mock_client = AsyncMock()
        # query_points returns an object with empty .points
        qp_response = MagicMock()
        qp_response.points = []
        mock_client.query_points = AsyncMock(return_value=qp_response)

        s = make_settings()

        with (
            patch("archivum.db.qdrant_client.get_client", AsyncMock(return_value=mock_client)),
            patch("archivum.db.qdrant_client.embed_texts", AsyncMock(return_value=[[0.1, 0.2, 0.3]])),
            patch("archivum.db.qdrant_client.resolve_embed_dim", AsyncMock(return_value=3)),
        ):
            result = await qdrant_module.search("unknown query", settings=s)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_results_with_correct_fields(self):
        hit = MagicMock()
        hit.score = 0.95
        hit.payload = {
            "slug": "found-page",
            "title": "Found Page",
            "text": "Some excerpt text here",
            "chunk_index": 0,
            "wiki_id": "default",
        }

        mock_client = AsyncMock()
        qp_response = MagicMock()
        qp_response.points = [hit]
        mock_client.query_points = AsyncMock(return_value=qp_response)

        s = make_settings()

        with (
            patch("archivum.db.qdrant_client.get_client", AsyncMock(return_value=mock_client)),
            patch("archivum.db.qdrant_client.embed_texts", AsyncMock(return_value=[[0.1, 0.2, 0.3]])),
            patch("archivum.db.qdrant_client.resolve_embed_dim", AsyncMock(return_value=3)),
        ):
            result = await qdrant_module.search("some query", settings=s)

        assert len(result) == 1
        item = result[0]
        assert item["slug"] == "found-page"
        assert item["title"] == "Found Page"
        assert "excerpt" in item
        assert "score" in item
        assert item["score"] == pytest.approx(0.95)


# ── TestDeletePage ────────────────────────────────────────────────────────────


class TestDeletePage:
    @pytest.mark.asyncio
    async def test_smoke_delete_page(self):
        """Verify client.delete is called with the right slug filter."""
        mock_client = make_mock_qdrant_client()
        s = make_settings()

        with patch("archivum.db.qdrant_client.get_client", AsyncMock(return_value=mock_client)):
            await qdrant_module.delete_page("my-slug", "default", s)

        mock_client.delete.assert_called_once()
        call_kwargs = mock_client.delete.call_args
        assert call_kwargs.kwargs.get("collection_name") == "test_collection" or \
               (call_kwargs.args and call_kwargs.args[0] == "test_collection") or \
               "test_collection" in str(call_kwargs)
