"""Bounded hybrid retrieval for natural-language knowledge requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from archivum.config import Settings
from archivum.db import qdrant_client as qdrant
from archivum.db import sqlite
from archivum.knowledge.models import Citation, ContextNode
from archivum.knowledge.personal_root import SELF_ID
from archivum.knowledge.repository import KnowledgeRepository
from archivum.retrieval.context import ContextRequest, build_context_package


_RRF_K = 60
_CHANNEL_WEIGHTS = {"keyword": 1.0, "vector": 1.0, "graph": 0.8}
_PAGE_PREFIX = "page:"
_GRAPH_NEIGHBOR_RESERVE = 4


@dataclass(frozen=True)
class HybridHit:
    id: str
    label: str
    score: float
    source: str
    citation: Citation
    raw_score: float = 0.0


def fuse_ranked_hits(
    *,
    keyword: list[tuple[str, float]],
    vector: list[tuple[str, float]],
    graph: list[tuple[str, float]],
    limit: int = 10,
) -> list[HybridHit]:
    """Fuse ranked channels with weighted reciprocal rank fusion.

    Input scores deliberately do not affect RRF: each channel has already
    established its own ordering and may use a different score scale.
    """
    scores: dict[str, float] = {}
    channels: dict[str, list[str]] = {}
    for channel_name, ranked_hits in (
        ("keyword", keyword),
        ("vector", vector),
        ("graph", graph),
    ):
        weight = _CHANNEL_WEIGHTS[channel_name]
        seen: set[str] = set()
        for rank, (hit_id, _) in enumerate(ranked_hits, start=1):
            if not hit_id or hit_id in seen:
                continue
            seen.add(hit_id)
            scores[hit_id] = scores.get(hit_id, 0.0) + weight / (_RRF_K + rank)
            channels.setdefault(hit_id, []).append(channel_name)

    fused = [
        HybridHit(
            id=hit_id,
            label=hit_id,
            score=score,
            source="+".join(channels[hit_id]),
            citation=_fallback_citation(hit_id),
        )
        for hit_id, score in scores.items()
    ]
    return sorted(fused, key=lambda hit: (-hit.score, hit.id))[: max(limit, 0)]


async def hybrid_retrieve(
    query: str,
    wiki_id: str,
    limit: int = 10,
    *,
    settings: Settings | None = None,
) -> list[HybridHit]:
    """Retrieve cited page and graph evidence without expanding beyond a wiki.

    Dense search supplies natural-language excerpts, FTS supplies exact-term
    matches, and cited canonical records expand the strongest page seeds.
    """
    query = query.strip()
    if not query or limit <= 0:
        return []

    channel_limit = max(limit, 10)
    vector_rows, keyword_rows = await asyncio.gather(
        _vector_rows(query, wiki_id, channel_limit, settings),
        _keyword_rows(query, wiki_id, channel_limit),
    )
    metadata = _page_metadata(vector_rows, keyword_rows, wiki_id)
    seed_limit = max(1, channel_limit - _GRAPH_NEIGHBOR_RESERVE)
    seed_ids = [SELF_ID, *metadata][:seed_limit]
    graph_nodes = await _graph_nodes(query, wiki_id, seed_ids, channel_limit)

    fused = fuse_ranked_hits(
        vector=[
            (_result_id(wiki_id, row["slug"]), float(row.get("score", 0.0)))
            for row in vector_rows
            if row.get("slug")
        ],
        keyword=[
            (_page_id(wiki_id, row["slug"]), float(-index))
            for index, row in enumerate(keyword_rows, start=1)
            if row.get("slug")
        ],
        graph=[(node.id, float(-index)) for index, node in enumerate(graph_nodes, start=1)],
        limit=limit,
    )
    graph_by_id = {node.id: node for node in graph_nodes}
    return [_enrich_hit(hit, metadata.get(hit.id), graph_by_id.get(hit.id)) for hit in fused]


async def _vector_rows(
    query: str, wiki_id: str, limit: int, settings: Settings | None
) -> list[dict]:
    try:
        return await qdrant.search(query, wiki_id=wiki_id, limit=limit, settings=settings)
    except Exception:
        return []


async def _keyword_rows(query: str, wiki_id: str, limit: int) -> list[dict]:
    try:
        return await sqlite.search_pages_fts(query, wiki_id=wiki_id, limit=limit)
    except Exception:
        return []


async def _graph_nodes(
    query: str, wiki_id: str, seed_ids: list[str], limit: int
) -> list[ContextNode]:
    try:
        async with sqlite.get_db() as connection:
            package = await build_context_package(
                KnowledgeRepository(connection),
                ContextRequest(
                    query=query,
                    scope=f"wiki:{wiki_id}",
                    seed_ids=seed_ids,
                    depth=1,
                    max_nodes=limit,
                ),
            )
        return package.nodes if not package.insufficient_evidence else []
    except Exception:
        # Canonical knowledge is an independently rebuildable retrieval signal.
        return []


def _page_metadata(
    vector_rows: list[dict], keyword_rows: list[dict], wiki_id: str
) -> dict[str, dict]:
    metadata: dict[str, dict] = {}
    for row in keyword_rows:
        slug = row.get("slug")
        if slug:
            metadata[_page_id(wiki_id, slug)] = row
    for row in vector_rows:
        slug = row.get("slug")
        if slug:
            # Vector excerpts are source chunks, so preserve them over FTS snippets.
            metadata[_result_id(wiki_id, slug)] = row
    return metadata


def _enrich_hit(
    hit: HybridHit, page: dict | None, node: ContextNode | None
) -> HybridHit:
    if page is not None:
        excerpt = str(page.get("excerpt") or "").strip()
        return HybridHit(
            id=hit.id,
            label=str(page.get("title") or hit.id),
            score=hit.score,
            source=hit.source,
            citation=Citation(
                source_id=hit.id,
                chunk_id=f"{hit.id}:chunk:{page.get('chunk_index', 0)}",
                span_start=None,
                span_end=None,
                quote=excerpt or None,
            ),
            raw_score=float(page.get("score", 0.0)),
        )
    if node is not None and node.citations:
        return HybridHit(
            id=hit.id,
            label=node.label,
            score=hit.score,
            source=hit.source,
            citation=node.citations[0],
            raw_score=hit.raw_score,
        )
    return hit


def _page_id(wiki_id: str, slug: str) -> str:
    return f"{_PAGE_PREFIX}{wiki_id}:{slug}"


def _result_id(wiki_id: str, slug: str) -> str:
    return slug if ":" in slug else _page_id(wiki_id, slug)


def _fallback_citation(hit_id: str) -> Citation:
    return Citation(
        source_id=hit_id,
        chunk_id=hit_id,
        span_start=None,
        span_end=None,
        quote=None,
    )
