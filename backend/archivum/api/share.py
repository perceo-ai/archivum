"""Public share routes: /api/share/*

Used by the read-only share page viewer (no auth required).
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from archivum.db import sqlite

router = APIRouter(prefix="/api/share", tags=["share"])
logger = logging.getLogger(__name__)


class SharePageResponse(BaseModel):
    type: str
    token: str
    wiki_id: str

    # page type
    slug: str | None = None
    title: str | None = None
    tags: list[str] = []
    content: str | None = None

    # diagnostics
    expires_at: str | None = None


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def _deserialize_tags(tags_raw: object) -> list[str]:
    if isinstance(tags_raw, list):
        return [str(t) for t in tags_raw]
    if tags_raw is None:
        return []
    if isinstance(tags_raw, str):
        try:
            parsed = json.loads(tags_raw)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except json.JSONDecodeError:
            return []
    return []


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        # Allow both ISO and sqlite datetime strings.
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return exp <= datetime.now(UTC)
    except Exception:
        return False


@router.get("/{token}", response_model=SharePageResponse)
async def get_share(token: str) -> SharePageResponse:
    if not _TOKEN_RE.match(token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Invalid share token", "code": "invalid_token"},
        )

    link = await sqlite.get_share_link(token)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Share link not found", "code": "share_not_found"},
        )

    if link.get("expires_at") and _is_expired(link.get("expires_at")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Share link expired", "code": "share_expired"},
        )

    link_type = str(link.get("type") or "page")
    if link_type != "page":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={"detail": f"Share type '{link_type}' not implemented", "code": "share_type_not_implemented"},
        )

    slug = link.get("target_id")
    if not slug or not isinstance(slug, str):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Share target missing", "code": "share_target_missing"},
        )

    page = await sqlite.get_page(slug, link.get("wiki_id") or "default")
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Shared page not found", "code": "shared_page_not_found"},
        )

    return SharePageResponse(
        type=link_type,
        token=token,
        wiki_id=str(link.get("wiki_id") or "default"),
        slug=page.get("slug"),
        title=page.get("title"),
        content=page.get("content"),
        tags=_deserialize_tags(page.get("tags")),
        expires_at=link.get("expires_at"),
    )

