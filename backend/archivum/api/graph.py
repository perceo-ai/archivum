from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from archivum.auth import CurrentUser, get_current_user
from archivum.db import graph

# Repo-owned mock fixtures (no Kuzu DB required)
from archivum.scripts.graph_export import DEMO_GRAPH

router = APIRouter(prefix="/api", tags=["graph"])

logger = logging.getLogger(__name__)


def _format_edges(data: dict) -> list[dict]:
    # Frontend expects edges with `label`
    return [
        {"from": e["from"], "to": e["to"], "label": e.get("type", "")}
        for e in data.get("edges", [])
        if e.get("from") and e.get("to")
    ]


@router.get("/graph")
async def get_graph(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        data = await graph.get_all_nodes_edges(current_user.wiki_id)
    except Exception as e:
        # Local/mock-safe fallback: if Kuzu isn't configured, still return a usable demo graph.
        logger.warning("graph.get_all_nodes_edges failed; falling back to demo graph", extra={"error": str(e)})
        data = DEMO_GRAPH

    return {"nodes": data.get("nodes", []), "edges": _format_edges(data)}


@router.get("/graph/demo")
async def get_graph_demo(current_user: CurrentUser = Depends(get_current_user)) -> dict:
    """Explicit demo graph endpoint (no DB required)."""
    data = DEMO_GRAPH
    return {"nodes": data.get("nodes", []), "edges": _format_edges(data)}


@router.get("/graph/neighbors")
async def graph_neighbors(
    node_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        data = await graph.get_neighbors(node_id, current_user.wiki_id)
    except Exception as e:
        logger.warning("graph.get_neighbors failed; returning empty neighbors", extra={"error": str(e), "node_id": node_id})
        data = {"center": node_id, "nodes": [], "edges": []}

    return {
        "center": data.get("center"),
        "nodes": data.get("nodes", []),
        "edges": _format_edges(data),
    }

