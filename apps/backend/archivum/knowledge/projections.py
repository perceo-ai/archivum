"""Rebuild Kuzu and Qdrant projections from canonical knowledge records."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from archivum.db.graph import (
    add_knowledge_relationship,
    add_mention,
    add_reference,
    clear_knowledge_projection,
    upsert_entity,
    upsert_knowledge_node,
    upsert_page,
)
from archivum.db.qdrant_client import index_page
from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.repository import KnowledgeRepository


_QDRANT_KINDS = frozenset({"page", "source", "claim"})
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectionReport:
    objects: int
    relationships: int
    kuzu_nodes: int
    kuzu_edges: int
    qdrant_indexed: int


def _citations_payload(citations: list[Citation]) -> list[dict[str, Any]]:
    return [citation.model_dump() for citation in citations]


def _page_slug(object_: KnowledgeObject) -> str:
    return str(object_.properties.get("slug") or object_.id)


def _qdrant_content(object_: KnowledgeObject) -> str:
    for key in ("markdown", "content", "text"):
        value = object_.properties.get(key)
        if isinstance(value, str) and value.strip():
            return value
    evidence = "\n".join(citation.quote or "" for citation in object_.citations).strip()
    return evidence or object_.label


async def _project_kuzu(operation, *args) -> bool:
    """Keep canonical data usable when the rebuildable graph is unavailable."""
    try:
        await operation(*args)
        return True
    except Exception as exc:
        logger.warning("Kuzu projection operation failed: %s", exc)
        return False


async def rebuild_knowledge_projections(
    repo: KnowledgeRepository, wiki_id: str
) -> ProjectionReport:
    """Project canonical knowledge into rebuildable graph and semantic indexes."""
    objects = await repo.list_objects(limit=100_000)
    relationships = await repo.list_relationships()
    objects_by_id = {object_.id: object_ for object_ in objects}

    graph_available = await _project_kuzu(clear_knowledge_projection, wiki_id)
    kuzu_nodes = 0
    for object_ in objects:
        node_projected = await _project_kuzu(
            upsert_knowledge_node,
            object_.id,
            object_.label,
            object_.kind,
            object_.scope,
            object_.confidence,
            object_.extraction_method,
            _citations_payload(object_.citations),
            wiki_id,
        )
        kuzu_nodes += int(node_projected)
        if object_.kind == "page":
            await _project_kuzu(upsert_page, _page_slug(object_), object_.label, wiki_id)
        else:
            await _project_kuzu(upsert_entity, object_.id, object_.kind, wiki_id)

    qdrant_indexed = 0
    for object_ in objects:
        if object_.kind not in _QDRANT_KINDS:
            continue
        indexed = await index_page(
            object_.id,
            object_.label,
            _qdrant_content(object_),
            wiki_id,
        )
        qdrant_indexed += indexed if isinstance(indexed, int) else 1

    kuzu_edges = 0
    for relationship in relationships:
        relationship_projected = await _project_kuzu(
            add_knowledge_relationship,
            relationship.src_id,
            relationship.dst_id,
            relationship.id,
            relationship.rel_type,
            relationship.scope,
            relationship.confidence,
            relationship.extraction_method,
            _citations_payload(relationship.citations),
        )
        kuzu_edges += int(relationship_projected)

        source = objects_by_id.get(relationship.src_id)
        destination = objects_by_id.get(relationship.dst_id)
        if source is None or destination is None:
            continue
        if source.kind == "page" and destination.kind == "page" and relationship.rel_type == "references":
            await _project_kuzu(add_reference, _page_slug(source), _page_slug(destination), wiki_id)
        elif source.kind == "page" and destination.kind != "page" and relationship.rel_type == "mentions":
            await _project_kuzu(add_mention, _page_slug(source), destination.id, wiki_id)

    return ProjectionReport(
        objects=len(objects),
        relationships=len(relationships),
        kuzu_nodes=kuzu_nodes if graph_available else 0,
        kuzu_edges=kuzu_edges if graph_available else 0,
        qdrant_indexed=qdrant_indexed,
    )
