"""Build bounded, evidence-backed context packages from knowledge records."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from collections.abc import Iterable

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


@dataclass(frozen=True)
class ContextRequest:
    query: str
    scope: str | None
    source_type: str | None = None
    depth: int = 2
    max_nodes: int = 10
    relations: list[str] | None = None
    seed_ids: list[str] | None = None


async def build_context_package(
    repo: KnowledgeRepository, request: ContextRequest
) -> ContextPackage:
    """Return a bounded, scoped subgraph rooted in requested or matched knowledge."""
    objects = await repo.list_objects(scope=request.scope)
    objects_by_id = {obj.id: obj for obj in objects}
    seeds = _select_seeds(objects, request)
    if not seeds:
        root = objects_by_id.get(SELF_ID)
        if root is not None:
            seeds = [SELF_ID]

    visited, edges = await _expand(repo, objects_by_id, seeds, request)
    nodes = [_context_node(objects_by_id[node_id]) for node_id in visited]
    context_edges = [_context_edge(rel) for rel in edges]
    citations = _unique_citations(
        citation for node in nodes for citation in node.citations
    )
    citations = _unique_citations(
        [*citations, *(citation for edge in context_edges for citation in edge.citations)]
    )

    insufficient_evidence = not any(node.citations for node in nodes)
    return ContextPackage(
        query=request.query,
        seeds=seeds,
        nodes=nodes,
        edges=context_edges,
        citations=citations,
        insufficient_evidence=insufficient_evidence,
        reason=("No cited knowledge objects matched the requested context." if insufficient_evidence else None),
    )


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


async def _expand(
    repo: KnowledgeRepository,
    objects_by_id: dict[str, KnowledgeObject],
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
        for relationship in await repo.list_relationships(node_id=node_id, scope=request.scope):
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
