"""Qdrant wrapper: collection management, upsert, search, delete."""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import Any

from fastembed import TextEmbedding
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from archivum.config import Settings, get_settings

logger = logging.getLogger(__name__)

# ── Module-level singletons ───────────────────────────────────────────────────

_client: AsyncQdrantClient | None = None
_embedder: TextEmbedding | None = None


def get_embedder(settings: Settings | None = None) -> TextEmbedding:
    global _embedder
    if _embedder is None:
        s = settings or get_settings()
        _embedder = TextEmbedding(s.embed_model)
    return _embedder


async def get_client(settings: Settings | None = None) -> AsyncQdrantClient:
    global _client
    if _client is None:
        s = settings or get_settings()
        _client = AsyncQdrantClient(url=s.qdrant_url)
    return _client


# ── Chunking ─────────────────────────────────────────────────────────────────

def _chunk_text(text: str, chunk_size: int = 512, overlap: int = 64) -> list[str]:
    """Split *text* into overlapping token-approximate chunks.

    We approximate tokens as whitespace-separated words (1 word ≈ 1.3 tokens).
    """
    words = text.split()
    chunks: list[str] = []
    step = max(1, chunk_size - overlap)
    i = 0
    while i < len(words):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk.strip():
            chunks.append(chunk.strip())
        i += step
    return chunks or [text[:2000]]  # fallback for very short docs


# ── Embedding helper ─────────────────────────────────────────────────────────

async def embed_texts(texts: list[str], settings: Settings | None = None) -> list[list[float]]:
    """Embed *texts* using fastembed (sync, runs in executor)."""
    loop = asyncio.get_running_loop()
    embedder = get_embedder(settings)

    def _embed() -> list[list[float]]:
        return [v.tolist() for v in embedder.embed(texts)]

    return await loop.run_in_executor(None, _embed)


# ── Collection init ───────────────────────────────────────────────────────────

async def init_collection(settings: Settings | None = None) -> None:
    """Create the Qdrant collection if it does not already exist."""
    s = settings or get_settings()
    client = await get_client(s)

    try:
        exists = await client.collection_exists(s.qdrant_collection)
        if not exists:
            await client.create_collection(
                collection_name=s.qdrant_collection,
                vectors_config=VectorParams(
                    size=s.embed_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection '%s'", s.qdrant_collection)
        else:
            logger.info("Qdrant collection '%s' already exists", s.qdrant_collection)
    except Exception as exc:
        logger.warning("Could not init Qdrant collection: %s", exc)


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def upsert_page(
    slug: str,
    title: str,
    content: str,
    wiki_id: str = "default",
    settings: Settings | None = None,
) -> int:
    """Chunk *content*, embed all chunks, upsert to Qdrant. Returns chunk count."""
    s = settings or get_settings()
    client = await get_client(s)

    # Delete stale vectors first
    await delete_page(slug, wiki_id, s)

    chunks = _chunk_text(content)
    vectors = await embed_texts(chunks, s)

    points = [
        PointStruct(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{wiki_id}/{slug}/{i}")),
            vector=vec,
            payload={
                "slug": slug,
                "title": title,
                "chunk_index": i,
                "wiki_id": wiki_id,
                "text": chunk,
            },
        )
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]

    await client.upsert(collection_name=s.qdrant_collection, points=points)
    return len(points)


async def search(
    query: str,
    wiki_id: str = "default",
    limit: int = 5,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Semantic search. Returns list of {slug, title, excerpt, score}."""
    s = settings or get_settings()
    client = await get_client(s)

    vectors = await embed_texts([query], s)
    query_vec = vectors[0]

    results = await client.search(
        collection_name=s.qdrant_collection,
        query_vector=query_vec,
        query_filter=Filter(
            must=[FieldCondition(key="wiki_id", match=MatchValue(value=wiki_id))]
        ),
        limit=limit,
        with_payload=True,
    )

    seen: dict[str, dict[str, Any]] = {}
    for hit in results:
        payload = hit.payload or {}
        slug = payload.get("slug", "")
        if slug not in seen or hit.score > seen[slug]["score"]:
            seen[slug] = {
                "slug": slug,
                "title": payload.get("title", ""),
                "excerpt": payload.get("text", "")[:300],
                "score": hit.score,
                "chunk_index": payload.get("chunk_index", 0),
            }

    return sorted(seen.values(), key=lambda x: x["score"], reverse=True)


async def search_raw(
    query: str,
    wiki_id: str = "default",
    limit: int = 5,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Like search() but returns all individual chunk hits (for context building)."""
    s = settings or get_settings()
    client = await get_client(s)

    vectors = await embed_texts([query], s)
    results = await client.search(
        collection_name=s.qdrant_collection,
        query_vector=vectors[0],
        query_filter=Filter(
            must=[FieldCondition(key="wiki_id", match=MatchValue(value=wiki_id))]
        ),
        limit=limit * 3,  # fetch more to allow deduplication upstream
        with_payload=True,
    )

    return [
        {
            "slug": (r.payload or {}).get("slug", ""),
            "title": (r.payload or {}).get("title", ""),
            "excerpt": (r.payload or {}).get("text", ""),
            "score": r.score,
            "chunk_index": (r.payload or {}).get("chunk_index", 0),
        }
        for r in results
    ]


async def delete_page(
    slug: str,
    wiki_id: str = "default",
    settings: Settings | None = None,
) -> None:
    """Delete all vectors for the given slug + wiki_id."""
    s = settings or get_settings()
    client = await get_client(s)
    try:
        from qdrant_client.models import FilterSelector
        await client.delete(
            collection_name=s.qdrant_collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="slug", match=MatchValue(value=slug)),
                        FieldCondition(key="wiki_id", match=MatchValue(value=wiki_id)),
                    ]
                )
            ),
        )
    except Exception as exc:
        logger.warning("Could not delete vectors for %s/%s: %s", wiki_id, slug, exc)
