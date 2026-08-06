from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import aiosqlite

from archivum.archgraph.lexical import score_nodes, trigram_candidates

_TOP_SEEDS = 3


@dataclass
class ScopedSubgraph:
    nodes: list[dict] = field(default_factory=list)
    edges: list[dict] = field(default_factory=list)


async def retrieve_code(
    conn: aiosqlite.Connection,
    query: str,
    *,
    adjacency: dict[str, list[dict]],
    node_meta: dict[str, dict],
    depth: int = 2,
    max_nodes: int = 10,
    scope: str | None = None,
    relations: frozenset[str] | None = None,
) -> ScopedSubgraph:
    """Retrieve a scoped subgraph via lexical seed selection + BFS expansion.

    Algorithm:
    1. Seeds: trigram_candidates → score_nodes → top-3 node ids.
       If scope given, keep only seeds whose node_meta scope == scope.
    2. BFS from seeds over adjacency up to `depth` hops.
       Only traverse edges whose relation ∈ relations (if given) and whose
       target's node_meta scope == scope (if given).
    3. Truncate visited set to max_nodes ordered by (BFS distance asc,
       seed score desc).
    4. Build nodes list from node_meta; edges list = adjacency edges among
       kept nodes respecting the relations filter.
    """
    # ---- Step 1: seed selection ----
    candidates = await trigram_candidates(conn, query)
    scored = await score_nodes(conn, query, candidates)  # [(score, node_id), ...]

    # filter to nodes known in node_meta
    scored = [(s, nid) for s, nid in scored if nid in node_meta]

    # apply scope filter on seeds
    if scope is not None:
        scored = [(s, nid) for s, nid in scored if node_meta[nid].get("scope") == scope]

    seeds_ordered = [nid for _, nid in scored[:_TOP_SEEDS]]
    seed_score: dict[str, float] = {nid: s for s, nid in scored[:_TOP_SEEDS]}

    # ---- Step 2: BFS ----
    # visited: node_id -> (bfs_distance, seed_score_for_ordering)
    # We use the seed's score for the node that introduced it (seeds have their own score;
    # non-seed expanded nodes inherit the seed score of the path that found them).
    visited_order: list[tuple[int, float, str]] = []  # (dist, -seed_score, node_id)
    visited: dict[str, tuple[int, float]] = {}  # node_id -> (dist, seed_score)

    queue: deque[tuple[str, int, float]] = deque()
    for nid in seeds_ordered:
        if nid not in node_meta:
            continue
        sc = seed_score.get(nid, 0.0)
        visited[nid] = (0, sc)
        queue.append((nid, 0, sc))

    while queue:
        current, dist, sc = queue.popleft()
        if dist >= depth:
            continue
        for edge in adjacency.get(current, []):
            target = edge["target"]
            if target in visited:
                continue
            if relations is not None and edge.get("relation") not in relations:
                continue
            if target not in node_meta:
                continue
            if scope is not None and node_meta[target].get("scope") != scope:
                continue
            visited[target] = (dist + 1, sc)
            queue.append((target, dist + 1, sc))

    # ---- Step 3: truncate ----
    # Sort by (dist asc, seed_score desc, node_id asc) for determinism
    sorted_nodes = sorted(
        visited.items(),
        key=lambda item: (item[1][0], -item[1][1], item[0]),
    )
    kept_ids: set[str] = {nid for nid, _ in sorted_nodes[:max_nodes]}

    # ---- Step 4: build result ----
    nodes: list[dict] = []
    for nid, _ in sorted_nodes[:max_nodes]:
        meta = node_meta[nid]
        citation = meta.get("citation") or nid
        nodes.append(
            {
                "id": nid,
                "label": meta.get("label", nid),
                "kind": meta.get("kind", ""),
                "scope": meta.get("scope", ""),
                "confidence": meta.get("confidence", 1.0),
                "extraction_method": meta.get("extraction_method", ""),
                "citation": citation,
            }
        )

    edges: list[dict] = []
    for nid in kept_ids:
        for edge in adjacency.get(nid, []):
            target = edge["target"]
            if target not in kept_ids:
                continue
            if relations is not None and edge.get("relation") not in relations:
                continue
            edges.append(
                {
                    "source": nid,
                    "target": target,
                    "relation": edge.get("relation", ""),
                    "extraction_method": edge.get("extraction_method", ""),
                    "confidence": edge.get("confidence", 1.0),
                }
            )

    return ScopedSubgraph(nodes=nodes, edges=edges)
