from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends

from archivum.auth import CurrentUser, require_owner
from archivum.config import Settings, get_settings
from archivum.db import graph, qdrant_client as qdrant, sqlite

router = APIRouter(prefix="/api", tags=["system"])


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


@router.post("/rebuild-indexes")
async def rebuild_indexes(
    current_user: CurrentUser = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pages = await sqlite.list_pages(current_user.wiki_id)

    # Re-init derived stores
    await qdrant.init_collection(settings)
    await graph.init_graph(settings)

    for p in pages:
        await qdrant.upsert_page(p["slug"], p["title"], p.get("content", ""), current_user.wiki_id, settings)
        await graph.upsert_page(p["slug"], p["title"], current_user.wiki_id)

        # Rebuild REFERENCES edges from wikilinks
        content = p.get("content", "") or ""
        for target in WIKILINK_RE.findall(content):
            target_slug = target.strip()
            if not target_slug:
                continue
            existing = await sqlite.get_page(target_slug, current_user.wiki_id)
            if existing:
                await graph.add_reference(p["slug"], target_slug, current_user.wiki_id)

    return {"detail": "Rebuilt indexes", "pages": len(pages)}


@router.get("/lint")
async def lint_wiki(
    current_user: CurrentUser = Depends(require_owner),
) -> dict[str, Any]:
    pages = await sqlite.list_pages(current_user.wiki_id)
    slug_set = {p["slug"] for p in pages}

    inbound: dict[str, int] = {s: 0 for s in slug_set}
    outbound: dict[str, int] = {s: 0 for s in slug_set}
    broken: list[dict[str, Any]] = []

    for p in pages:
        slug = p["slug"]
        content = p.get("content", "") or ""
        targets = [t.strip() for t in WIKILINK_RE.findall(content)]
        for t in targets:
            if not t:
                continue
            outbound[slug] = outbound.get(slug, 0) + 1
            if t in slug_set:
                inbound[t] = inbound.get(t, 0) + 1
            else:
                broken.append(
                    {
                        "type": "broken_wikilink",
                        "page": slug,
                        "target": t,
                        "suggestion": f"Create page '{t}' or fix link.",
                    }
                )

    orphan_pages = [
        {
            "type": "orphan_page",
            "page": s,
            "suggestion": "Add links to/from other pages so this page is discoverable.",
        }
        for s in slug_set
        if inbound.get(s, 0) == 0 and outbound.get(s, 0) == 0
    ]

    issues = broken + orphan_pages
    return {"issues": issues, "counts": {"issues": len(issues)}}

