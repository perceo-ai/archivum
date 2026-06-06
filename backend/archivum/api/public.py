"""Public read-only routes for whole-wiki publishing."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from archivum.config import Settings, get_settings
from archivum.db import sqlite

router = APIRouter(prefix="/api/public", tags=["public"])


class PublicPageSummary(BaseModel):
    slug: str
    title: str
    tags: list[str]
    updated_at: str


class PublicPageDetail(PublicPageSummary):
    content: str


def _require_public_wiki(settings: Settings) -> None:
    if not settings.public_wiki_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Public wiki is disabled", "code": "public_wiki_disabled"},
        )


def _deserialize_tags(tags_raw: object) -> list[str]:
    if isinstance(tags_raw, list):
        return [str(t) for t in tags_raw]
    if isinstance(tags_raw, str):
        try:
            parsed = json.loads(tags_raw)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except json.JSONDecodeError:
            return []
    return []


@router.get("/pages", response_model=list[PublicPageSummary])
async def list_public_pages(
    settings: Settings = Depends(get_settings),
) -> list[PublicPageSummary]:
    _require_public_wiki(settings)
    rows = await sqlite.list_pages(settings.wiki_id)
    return [
        PublicPageSummary(
            slug=row["slug"],
            title=row["title"],
            tags=_deserialize_tags(row.get("tags")),
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


@router.get("/pages/{slug:path}", response_model=PublicPageDetail)
async def get_public_page(
    slug: str,
    settings: Settings = Depends(get_settings),
) -> PublicPageDetail:
    _require_public_wiki(settings)
    row = await sqlite.get_page(slug, settings.wiki_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Page '{slug}' not found", "code": "page_not_found"},
        )
    return PublicPageDetail(
        slug=row["slug"],
        title=row["title"],
        content=row["content"],
        tags=_deserialize_tags(row.get("tags")),
        updated_at=row["updated_at"],
    )
