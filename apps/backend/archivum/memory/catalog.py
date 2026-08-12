"""Bring pre-existing memory under the asset registry.

Wiki pages, ingested sources, and code graphs were memory before the registry
existed. Cataloguing registers them as typed, governed assets so every memory
kind — not just distilled conversation memory — can be versioned, reviewed, and
bound to an agent. Re-running is idempotent: ids are derived, not generated.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import aiosqlite

from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.personal_root import ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository
from archivum.memory.registry import MemoryAssetRegistry

CODEGRAPH_SCOPE_PREFIX = "repo:"

# Pages that already back a distilled memory asset must not be re-registered as
# plain wiki assets, or one unit of memory would appear under two ids.
EXCLUDED_PAGE_PREFIXES = ("memory/", "skills/")

_CODEGRAPH_SAMPLE_CITATIONS = 5


@dataclass
class CatalogReport:
    wiki_assets: int = 0
    source_assets: int = 0
    codegraph_assets: int = 0
    asset_ids: list[str] = field(default_factory=list)


async def sync_catalog(
    conn: aiosqlite.Connection, *, wiki_id: str
) -> CatalogReport:
    """Register wiki pages, sources, and code graphs as memory assets."""
    registry = MemoryAssetRegistry(conn)
    repo = KnowledgeRepository(conn)
    report = CatalogReport()

    await ensure_personal_root(repo, wiki_id=wiki_id)
    await _catalog_pages(conn, registry, repo, wiki_id=wiki_id, report=report)
    await _catalog_sources(conn, registry, repo, wiki_id=wiki_id, report=report)
    await _catalog_codegraphs(conn, registry, repo, wiki_id=wiki_id, report=report)
    return report


# ── Wiki pages ────────────────────────────────────────────────────────────


async def _catalog_pages(
    conn: aiosqlite.Connection,
    registry: MemoryAssetRegistry,
    repo: KnowledgeRepository,
    *,
    wiki_id: str,
    report: CatalogReport,
) -> None:
    async with conn.execute(
        "SELECT slug, title FROM pages WHERE wiki_id=? ORDER BY slug ASC", (wiki_id,)
    ) as cursor:
        rows = await cursor.fetchall()

    for row in rows:
        slug = row["slug"]
        if slug.startswith(EXCLUDED_PAGE_PREFIXES):
            continue
        # The canonical page object already exists and is already owner-linked,
        # so the asset shares its id rather than duplicating the record.
        object_id = f"page:{wiki_id}:{slug}"
        canonical = await repo.get_object(object_id)
        citations = (
            canonical.citations
            if canonical is not None
            else [_self_citation(object_id, row["title"])]
        )
        await registry.register_asset(
            id=object_id,
            wiki_id=wiki_id,
            asset_type="wiki",
            layer="L1",
            name=row["title"],
            scope=f"wiki:{wiki_id}",
            status="active",
            page_slug=slug,
            summary="Editable markdown page.",
            tags=["wiki"],
            metadata={"slug": slug},
            citations=citations,
            change_note="Catalogued from the markdown vault",
        )
        report.wiki_assets += 1
        report.asset_ids.append(object_id)


# ── Ingested sources ──────────────────────────────────────────────────────


async def _catalog_sources(
    conn: aiosqlite.Connection,
    registry: MemoryAssetRegistry,
    repo: KnowledgeRepository,
    *,
    wiki_id: str,
    report: CatalogReport,
) -> None:
    async with conn.execute(
        "SELECT s.id, s.source_type, s.origin_uri, s.content_hash, s.version, "
        "       s.ingested_at, d.id AS document_id "
        "FROM sources AS s LEFT JOIN documents AS d ON d.source_id = s.id "
        "ORDER BY s.id ASC"
    ) as cursor:
        rows = await cursor.fetchall()

    for row in rows:
        asset_id = f"source:{row['id']}"
        citation = Citation(
            source_id=row["id"],
            chunk_id=row["document_id"] or row["id"],
            span_start=None,
            span_end=None,
            quote=row["origin_uri"],
        )
        obj = KnowledgeObject(
            id=asset_id,
            kind="memory_source",
            label=row["origin_uri"] or row["id"],
            scope=f"wiki:{wiki_id}",
            confidence=1.0,
            extraction_method="EXTRACTED",
            citations=[citation],
            properties={
                "layer": "L0",
                "source_id": row["id"],
                "source_type": row["source_type"],
                "content_hash": row["content_hash"],
                "version": row["version"],
            },
        )
        await repo.upsert_object(obj)
        await link_to_self(repo, asset_id, "owns_asset", citation=citation)
        await registry.register_asset(
            id=asset_id,
            wiki_id=wiki_id,
            asset_type="source",
            layer="L0",
            name=obj.label,
            scope=obj.scope,
            status="active",
            summary=f"{row['source_type']} source, version {row['version']}.",
            tags=["source", row["source_type"]],
            metadata={
                "source_id": row["id"],
                "content_hash": row["content_hash"],
                "ingested_at": row["ingested_at"],
            },
            citations=[citation],
            change_note="Catalogued from the evidence store",
        )
        report.source_assets += 1
        report.asset_ids.append(asset_id)


# ── Code graphs ───────────────────────────────────────────────────────────


async def _catalog_codegraphs(
    conn: aiosqlite.Connection,
    registry: MemoryAssetRegistry,
    repo: KnowledgeRepository,
    *,
    wiki_id: str,
    report: CatalogReport,
) -> None:
    async with conn.execute(
        "SELECT DISTINCT scope FROM knowledge_objects WHERE scope LIKE ? ORDER BY scope ASC",
        (f"{CODEGRAPH_SCOPE_PREFIX}%",),
    ) as cursor:
        scopes = [row["scope"] for row in await cursor.fetchall()]

    for scope in scopes:
        nodes = await repo.list_objects(scope=scope, limit=10_000)
        edges = await repo.list_relationships(scope=scope)
        if not nodes:
            continue
        asset_id = f"codegraph:{scope}"
        citations = [
            node.citations[0]
            for node in nodes[:_CODEGRAPH_SAMPLE_CITATIONS]
            if node.citations
        ] or [_self_citation(asset_id, scope)]
        obj = KnowledgeObject(
            id=asset_id,
            kind="memory_codegraph",
            label=f"Code graph — {scope}",
            scope=f"wiki:{wiki_id}",
            confidence=1.0,
            extraction_method="EXTRACTED",
            citations=citations,
            properties={
                "layer": "L2",
                "repo_scope": scope,
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        )
        await repo.upsert_object(obj)
        await link_to_self(repo, asset_id, "uses_code", citation=citations[0])
        await registry.register_asset(
            id=asset_id,
            wiki_id=wiki_id,
            asset_type="codegraph",
            layer="L2",
            name=obj.label,
            scope=obj.scope,
            status="active",
            summary=f"{len(nodes)} code records and {len(edges)} relationships.",
            tags=["codegraph"],
            metadata={
                "repo_scope": scope,
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
            citations=citations,
            change_note="Catalogued from the code graph",
        )
        report.codegraph_assets += 1
        report.asset_ids.append(asset_id)


def _self_citation(object_id: str, quote: str) -> Citation:
    return Citation(
        source_id=object_id,
        chunk_id=object_id,
        span_start=None,
        span_end=None,
        quote=quote,
    )
