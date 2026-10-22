"""Graph calls from processes that may not open Kuzu themselves.

Kuzu lets one process hold its file, and this API is that process. The MCP
server runs with ``kuzu_role="client"`` and sends each graph call here
instead of opening the file. Only the API mounts this router; the MCP server
calls it and never serves it.

Most of these operations write or delete graph state, and the API's port may
be published beyond the compose network, so every call must carry the shared
token. With no token configured the router refuses everything rather than
trusting the network. It runs only the named graph operations below, never an
arbitrary attribute of the graph module.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request

from archivum.config import get_settings
from archivum.db import graph

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/graph", tags=["internal"])

_ALLOWED_OPS = frozenset(
    {
        "upsert_page",
        "upsert_entity",
        "upsert_knowledge_node",
        "add_knowledge_relationship",
        "clear_knowledge_projection",
        "clear_legacy_projection",
        "add_reference",
        "clear_references_from_page",
        "add_mention",
        "add_entity_relation",
        "get_neighbors",
        "get_backlinks",
        "get_all_nodes_edges",
        "delete_page_node",
        "rename_page_node",
        "cleanup_abandoned_nodes",
    }
)


@router.post("/{op}")
async def call_graph_op(
    op: str,
    request: Request,
    x_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if op not in _ALLOWED_OPS:
        raise HTTPException(status_code=404, detail=f"Unknown graph operation: {op}")

    expected = get_settings().internal_graph_token
    if not expected:
        raise HTTPException(status_code=403, detail="Internal graph token is not configured")
    if not secrets.compare_digest(x_internal_token or "", expected):
        raise HTTPException(status_code=403, detail="Invalid internal token")

    try:
        payload = await request.json()
    except ValueError:
        raise HTTPException(status_code=400, detail="Body must be a JSON object") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Body must be a JSON object")

    try:
        result = await getattr(graph, f"_local_{op}")(**payload)
    except Exception as exc:  # noqa: BLE001 - the caller gets a 503, not a traceback
        logger.warning("Internal graph op %s failed: %s", op, exc)
        raise HTTPException(status_code=503, detail=f"{op} failed: {exc}") from exc
    return {"result": result}
