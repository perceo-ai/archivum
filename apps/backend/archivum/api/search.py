from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from archivum.auth import CurrentUser, get_current_user
from archivum.config import Settings, get_settings
from archivum.retrieval.hybrid import hybrid_retrieve

router = APIRouter(prefix="/api", tags=["search"])


@router.get("/search")
async def search(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> list[dict]:
    """
    Hybrid semantic, keyword, and bounded graph search.

    Returns [{slug,title,excerpt,score}, ...]
    """
    q = q.strip()
    hits = await hybrid_retrieve(
        q, current_user.wiki_id, limit=limit, settings=settings
    )
    results: list[dict] = []
    for hit in hits:
        slug = _slug_from_page_id(hit.id, current_user.wiki_id)
        if slug is None:
            continue
        results.append(
            {
                "slug": slug,
                "title": hit.label,
                "excerpt": hit.citation.quote or "",
                "score": hit.raw_score,
            }
        )
    return results


def _slug_from_page_id(page_id: str, wiki_id: str) -> str | None:
    prefix = f"page:{wiki_id}:"
    return page_id.removeprefix(prefix) if page_id.startswith(prefix) else None
