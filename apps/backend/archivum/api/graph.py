from __future__ import annotations

from fastapi import APIRouter, Depends

from archivum.auth import CurrentUser, get_current_user
from archivum.db import graph

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
async def get_graph(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    data = await graph.get_all_nodes_edges(current_user.wiki_id)
    # Frontend expects edges with `label`
    edges = [
        {"from": e["from"], "to": e["to"], "label": e.get("type", "")}
        for e in data.get("edges", [])
        if e.get("from") and e.get("to")
    ]
    return {"nodes": data.get("nodes", []), "edges": edges}


@router.get("/graph/neighbors")
async def graph_neighbors(
    node_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    data = await graph.get_neighbors(node_id, current_user.wiki_id)
    edges = [
        {"from": e["from"], "to": e["to"], "label": e.get("type", "")}
        for e in data.get("edges", [])
        if e.get("from") and e.get("to")
    ]
    return {"center": data.get("center"), "nodes": data.get("nodes", []), "edges": edges}

