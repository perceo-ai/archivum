from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from archivum.auth import CurrentUser, get_current_user
from archivum.config import Settings, get_settings
from archivum.db import qdrant_client as qdrant
from archivum.db import sqlite

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """
    Semantic search via Qdrant (primary) with keyword FTS fallback.

    Returns [{slug,title,excerpt,score}, ...]
    """
    q = q.strip()
    results: list[dict] = []

    try:
        results = await qdrant.search(q, wiki_id=current_user.wiki_id, limit=limit, settings=settings)
    except Exception:
        results = []

    if len(results) < max(3, min(limit, 10)):
        # Fill remaining slots with keyword matches (dedup by slug)
        try:
            fts = await sqlite.search_pages_fts(q, wiki_id=current_user.wiki_id, limit=limit)
        except Exception:
            fts = []

        seen = {r.get("slug") for r in results if r.get("slug")}
        for row in fts:
            slug = row.get("slug")
            if not slug or slug in seen:
                continue
            results.append(
                {
                    "slug": slug,
                    "title": row.get("title", ""),
                    "excerpt": row.get("excerpt", ""),
                    "score": 0.0,
                }
            )
            seen.add(slug)
            if len(results) >= limit:
                break

    return results[:limit]

