"""Pages routes: /api/pages/*"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from archivum.auth import CurrentUser, get_current_user, require_writer
from archivum.config import Settings, get_settings
from archivum.db import sqlite, qdrant_client as qdrant, graph
from archivum.ingest.agent import slugify
from archivum.security.markdown import sanitize_markdown

router = APIRouter(prefix="/api/pages", tags=["pages"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PageSummary(BaseModel):
    slug: str
    title: str
    tags: list[str]
    created_at: str
    updated_at: str
    authored_by: str


class PageDetail(PageSummary):
    content: str
    id: int


class CreatePageRequest(BaseModel):
    title: str
    content: str = ""
    tags: list[str] = []
    slug: str | None = None


class UpdatePageRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    tags: list[str] | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

_SLUG_SEGMENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _validate_slug(slug: str) -> str:
    """
    Allow folder-like slugs: "projects/archivum/notes".
    Disallow traversal and weird separators.
    """
    if not slug or slug.strip() != slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Invalid slug", "code": "invalid_slug"},
        )
    if slug.startswith("/") or slug.endswith("/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Invalid slug", "code": "invalid_slug"},
        )
    if "\\" in slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Invalid slug", "code": "invalid_slug"},
        )

    parts = slug.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Invalid slug", "code": "invalid_slug"},
        )
    for p in parts:
        if not _SLUG_SEGMENT_RE.match(p):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": f"Invalid slug segment '{p}'", "code": "invalid_slug"},
            )
    return slug


def _deserialize_tags(tags_raw: str | list) -> list[str]:
    if isinstance(tags_raw, list):
        return tags_raw
    try:
        return json.loads(tags_raw)
    except (json.JSONDecodeError, TypeError):
        return []


def _row_to_summary(row: dict) -> PageSummary:
    return PageSummary(
        slug=row["slug"],
        title=row["title"],
        tags=_deserialize_tags(row["tags"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        authored_by=row["authored_by"],
    )


def _row_to_detail(row: dict) -> PageDetail:
    return PageDetail(
        id=row["id"],
        slug=row["slug"],
        title=row["title"],
        content=row["content"],
        tags=_deserialize_tags(row["tags"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        authored_by=row["authored_by"],
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[PageSummary])
async def list_pages(
    current_user: CurrentUser = Depends(get_current_user),
) -> list[PageSummary]:
    rows = await sqlite.list_pages(current_user.wiki_id)
    return [_row_to_summary(r) for r in rows]


@router.get("/{slug:path}/backlinks", response_model=list[dict])
async def get_backlinks(
    slug: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> list[dict]:
    slug = _validate_slug(slug)
    # Verify page exists
    existing = await sqlite.get_page(slug, current_user.wiki_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Page '{slug}' not found", "code": "page_not_found"},
        )
    return await graph.get_backlinks(slug, current_user.wiki_id)


@router.get("/{slug:path}", response_model=PageDetail)
async def get_page(
    slug: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> PageDetail:
    slug = _validate_slug(slug)
    row = await sqlite.get_page(slug, current_user.wiki_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Page '{slug}' not found", "code": "page_not_found"},
        )
    return _row_to_detail(row)


@router.post("", response_model=PageDetail, status_code=status.HTTP_201_CREATED)
async def create_page(
    body: CreatePageRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> PageDetail:
    logger.info(
        "API create_page",
        extra={"wiki_id": current_user.wiki_id, "title_chars": len(body.title or ""), "content_chars": len(body.content or "")},
    )
    raw_content = body.content or ""
    clean_content = sanitize_markdown(raw_content)

    # Derive slug
    slug = body.slug or slugify(body.title)
    if not slug:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Could not generate slug from title", "code": "invalid_title"},
        )
    slug = _validate_slug(slug)

    # Ensure uniqueness
    base_slug = slug
    counter = 2
    while await sqlite.get_page(slug, current_user.wiki_id):
        slug = f"{base_slug}-{counter}"
        counter += 1

    # Write to disk
    wiki_path = settings.wiki_dir / f"{slug}.md"
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(clean_content, encoding="utf-8")

    # SQLite
    page_id, _ = await sqlite.upsert_page(
        slug=slug,
        title=body.title,
        content=clean_content,
        tags=body.tags,
        authored_by="user",
        wiki_id=current_user.wiki_id,
    )

    # Qdrant
    await qdrant.upsert_page(slug, body.title, clean_content, current_user.wiki_id, settings)

    # Kuzu
    await graph.upsert_page(slug, body.title, current_user.wiki_id)

    row = await sqlite.get_page(slug, current_user.wiki_id)
    return _row_to_detail(row)  # type: ignore[arg-type]


@router.put("/{slug:path}", response_model=PageDetail)
async def update_page(
    slug: str,
    body: UpdatePageRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> PageDetail:
    slug = _validate_slug(slug)
    logger.info(
        "API update_page",
        extra={"wiki_id": current_user.wiki_id, "slug": slug, "has_title": body.title is not None, "has_content": body.content is not None},
    )
    existing = await sqlite.get_page(slug, current_user.wiki_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Page '{slug}' not found", "code": "page_not_found"},
        )

    new_title = body.title if body.title is not None else existing["title"]
    new_content_raw = body.content if body.content is not None else existing["content"]
    new_content = sanitize_markdown(new_content_raw)
    new_tags = body.tags if body.tags is not None else _deserialize_tags(existing["tags"])

    # Write to disk
    wiki_path = settings.wiki_dir / f"{slug}.md"
    wiki_path.write_text(new_content, encoding="utf-8")

    # SQLite
    await sqlite.upsert_page(
        slug=slug,
        title=new_title,
        content=new_content,
        tags=new_tags,
        authored_by="user",
        wiki_id=current_user.wiki_id,
    )

    # Qdrant — re-index
    await qdrant.upsert_page(slug, new_title, new_content, current_user.wiki_id, settings)

    # Kuzu — update page node
    await graph.upsert_page(slug, new_title, current_user.wiki_id)

    row = await sqlite.get_page(slug, current_user.wiki_id)
    return _row_to_detail(row)  # type: ignore[arg-type]


@router.delete("/{slug:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    slug: str,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> None:
    slug = _validate_slug(slug)
    logger.info("API delete_page", extra={"wiki_id": current_user.wiki_id, "slug": slug})
    existing = await sqlite.get_page(slug, current_user.wiki_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"Page '{slug}' not found", "code": "page_not_found"},
        )

    # Remove from disk
    wiki_path = settings.wiki_dir / f"{slug}.md"
    wiki_path.unlink(missing_ok=True)

    # SQLite
    await sqlite.delete_page(slug, current_user.wiki_id)

    # Qdrant
    await qdrant.delete_page(slug, current_user.wiki_id, settings)

    # Kuzu
    await graph.delete_page_node(slug)

    # Cleanup: remove graph nodes that no longer have any backing Page.
    await graph.cleanup_abandoned_nodes(current_user.wiki_id)
