"""Build bounded, evidence-backed context packages from knowledge records."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

import aiosqlite

from archivum.archgraph.retrieval import ScopedSubgraph, retrieve_code
from archivum.knowledge.models import (
    Citation,
    ContextEdge,
    ContextNode,
    ContextPackage,
    KnowledgeObject,
    KnowledgeRelationship,
)
from archivum.knowledge.personal_root import SELF_ID
from archivum.knowledge.repository import KnowledgeRepository


_OBJECT_SCAN_LIMIT = 10_000


@dataclass(frozen=True)
class ContextRequest:
    query: str
    scope: str | None
    source_type: str | None = None
    depth: int = 2
    max_nodes: int = 10
    relations: list[str] | None = None
    seed_ids: list[str] | None = None
    code_connection: aiosqlite.Connection | None = None


async def build_context_package(
    repo: KnowledgeRepository, request: ContextRequest
) -> ContextPackage:
    """Return a bounded, scoped subgraph rooted in requested or matched knowledge."""
    all_objects = await repo.list_objects(
        scope=request.scope, limit=_OBJECT_SCAN_LIMIT
    )
    relationships = await repo.list_relationships(scope=request.scope)
    if _is_code_request(request):
        return await _build_code_context_package(
            repo, all_objects, relationships, request
        )

    objects = _filter_source_type(all_objects, request.source_type)
    objects_by_id = {obj.id: obj for obj in objects}
    seeds = _select_seeds(objects, request)
    if not seeds and request.source_type is None:
        root = next((obj for obj in all_objects if obj.id == SELF_ID), None)
        if root is not None:
            objects_by_id[root.id] = root
            seeds = [SELF_ID]

    visited, edges = _expand(objects_by_id, relationships, seeds, request)
    return _package_from_records(request.query, seeds, objects_by_id, visited, edges)


async def _build_code_context_package(
    repo: KnowledgeRepository,
    objects: list[KnowledgeObject],
    relationships: list[KnowledgeRelationship],
    request: ContextRequest,
) -> ContextPackage:
    objects_by_id = {obj.id: obj for obj in objects}
    explicit_seeds = [
        seed_id for seed_id in request.seed_ids or [] if seed_id in objects_by_id
    ]
    subgraph = await _retrieve_code_subgraph(repo, objects, relationships, request)
    if subgraph is None:
        return _build_canonical_code_fallback(objects_by_id, relationships, request)

    seeds = _bounded_unique([*explicit_seeds, *subgraph.seeds], request.max_nodes)
    node_ids = _bounded_unique(
        [*explicit_seeds, *(node["id"] for node in subgraph.nodes)],
        request.max_nodes,
    )

    if not node_ids and request.source_type is None:
        root = objects_by_id.get(SELF_ID)
        if root is not None:
            node_ids = [SELF_ID]
            seeds = [SELF_ID]

    edges_by_key = {
        (relationship.src_id, relationship.dst_id, relationship.rel_type): relationship
        for relationship in relationships
    }
    edges = [
        edges_by_key[(edge["source"], edge["target"], edge["relation"])]
        for edge in subgraph.edges
        if (edge["source"], edge["target"], edge["relation"]) in edges_by_key
        and edge["source"] in node_ids
        and edge["target"] in node_ids
    ]
    return _package_from_records(request.query, seeds, objects_by_id, node_ids, edges)


async def _retrieve_code_subgraph(
    repo: KnowledgeRepository,
    objects: list[KnowledgeObject],
    relationships: list[KnowledgeRelationship],
    request: ContextRequest,
) -> ScopedSubgraph | None:
    connection = request.code_connection or repo._conn
    if not await _has_lexical_index(connection):
        return None

    adjacency: dict[str, list[dict]] = {}
    node_meta = {
        obj.id: {
            "label": obj.label,
            "kind": obj.kind,
            "scope": obj.scope,
            "confidence": obj.confidence,
            "extraction_method": obj.extraction_method,
            "citation": obj.citations[0].chunk_id,
        }
        for obj in objects
    }
    for relationship in relationships:
        if relationship.src_id in node_meta and relationship.dst_id in node_meta:
            adjacency.setdefault(relationship.src_id, []).append(
                {
                    "target": relationship.dst_id,
                    "relation": relationship.rel_type,
                    "extraction_method": relationship.extraction_method,
                    "confidence": relationship.confidence,
                }
            )
    return await retrieve_code(
        connection,
        request.query,
        adjacency=adjacency,
        node_meta=node_meta,
        depth=request.depth,
        max_nodes=request.max_nodes,
        scope=request.scope,
        relations=frozenset(request.relations) if request.relations is not None else None,
    )


def _build_canonical_code_fallback(
    objects_by_id: dict[str, KnowledgeObject],
    relationships: list[KnowledgeRelationship],
    request: ContextRequest,
) -> ContextPackage:
    seeds = _select_seeds(list(objects_by_id.values()), request)
    if not seeds and request.source_type is None and SELF_ID in objects_by_id:
        seeds = [SELF_ID]
    node_ids, edges = _expand(objects_by_id, relationships, seeds, request)
    return _package_from_records(request.query, seeds, objects_by_id, node_ids, edges)


async def _has_lexical_index(connection: aiosqlite.Connection) -> bool:
    async with connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='code_node_text'"
    ) as cursor:
        return await cursor.fetchone() is not None


def _is_code_request(request: ContextRequest) -> bool:
    return request.source_type == "code" or (request.scope or "").startswith("repo:")


def _filter_source_type(
    objects: list[KnowledgeObject], source_type: str | None
) -> list[KnowledgeObject]:
    if source_type is None:
        return objects
    return [
        obj for obj in objects if obj.properties.get("source_type") == source_type
    ]


def _select_seeds(
    objects: list[KnowledgeObject], request: ContextRequest
) -> list[str]:
    available = {obj.id for obj in objects}
    seeds = [seed_id for seed_id in request.seed_ids or [] if seed_id in available]
    query = request.query.strip().casefold()
    if query:
        seeds.extend(
            obj.id
            for obj in objects
            if query in obj.label.casefold() and obj.id not in seeds
        )
    return seeds


def _expand(
    objects_by_id: dict[str, KnowledgeObject],
    relationships: list[KnowledgeRelationship],
    seeds: list[str],
    request: ContextRequest,
) -> tuple[list[str], list[KnowledgeRelationship]]:
    max_nodes = max(request.max_nodes, 0)
    if max_nodes == 0:
        return [], []

    allowed_relations = set(request.relations) if request.relations is not None else None
    visited: list[str] = []
    visited_ids: set[str] = set()
    queue: deque[tuple[str, int]] = deque()
    for seed_id in seeds:
        if seed_id in objects_by_id and seed_id not in visited_ids and len(visited) < max_nodes:
            visited.append(seed_id)
            visited_ids.add(seed_id)
            queue.append((seed_id, 0))

    traversed: dict[str, KnowledgeRelationship] = {}
    while queue:
        node_id, distance = queue.popleft()
        if distance >= max(request.depth, 0):
            continue
        for relationship in relationships:
            if node_id not in (relationship.src_id, relationship.dst_id):
                continue
            if allowed_relations is not None and relationship.rel_type not in allowed_relations:
                continue
            other_id = relationship.dst_id if relationship.src_id == node_id else relationship.src_id
            if other_id not in objects_by_id:
                continue
            if other_id not in visited_ids and len(visited) < max_nodes:
                visited.append(other_id)
                visited_ids.add(other_id)
                queue.append((other_id, distance + 1))
            if other_id in visited_ids:
                traversed[relationship.id] = relationship

    edges = [
        relationship
        for relationship in traversed.values()
        if relationship.src_id in visited_ids and relationship.dst_id in visited_ids
    ]
    return visited, edges


def _package_from_records(
    query: str,
    seeds: list[str],
    objects_by_id: dict[str, KnowledgeObject],
    node_ids: list[str],
    edges: list[KnowledgeRelationship],
) -> ContextPackage:
    nodes = [_context_node(objects_by_id[node_id]) for node_id in node_ids]
    context_edges = [_context_edge(relationship) for relationship in edges]
    citations = _unique_citations(
        citation for node in nodes for citation in node.citations
    )
    citations = _unique_citations(
        [*citations, *(citation for edge in context_edges for citation in edge.citations)]
    )
    insufficient_evidence = not any(node.citations for node in nodes)
    return ContextPackage(
        query=query,
        seeds=seeds,
        nodes=nodes,
        edges=context_edges,
        citations=citations,
        insufficient_evidence=insufficient_evidence,
        reason=(
            "No cited knowledge objects matched the requested context."
            if insufficient_evidence
            else None
        ),
    )


def _bounded_unique(ids: Iterable[str], max_nodes: int) -> list[str]:
    bounded: list[str] = []
    for node_id in ids:
        if node_id not in bounded and len(bounded) < max(max_nodes, 0):
            bounded.append(node_id)
    return bounded


def _context_node(obj: KnowledgeObject) -> ContextNode:
    return ContextNode(
        id=obj.id,
        label=obj.label,
        node_type=obj.kind,
        scope=obj.scope,
        extraction_method=obj.extraction_method,
        confidence=obj.confidence,
        citations=obj.citations,
    )


def _context_edge(relationship: KnowledgeRelationship) -> ContextEdge:
    return ContextEdge(
        from_id=relationship.src_id,
        to_id=relationship.dst_id,
        relation=relationship.rel_type,
        scope=relationship.scope,
        extraction_method=relationship.extraction_method,
        confidence=relationship.confidence,
        citations=relationship.citations,
    )


def _unique_citations(citations: Iterable[Citation]) -> list[Citation]:
    unique: list[Citation] = []
    seen: set[tuple[str, str, int | None, int | None, str | None]] = set()
    for citation in citations:
        key = (
            citation.source_id,
            citation.chunk_id,
            citation.span_start,
            citation.span_end,
            citation.quote,
        )
        if key not in seen:
            seen.add(key)
            unique.append(citation)
    return unique
