"""Unified activity stream.

The redesigned home screen is a single reverse-chronological feed rather than a
dashboard, so it needs page edits, agent suggestions, ingests, and newly
distilled memory in one ordered list. Each source is queried for a capped slice,
merged here, and truncated — the client never pages four cursors by hand.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from archivum.auth import CurrentUser, get_current_user
from archivum.db import sqlite
from archivum.knowledge.suggestions import SuggestionRepository
from archivum.memory.registry import MemoryAssetRegistry
from archivum.timestamps import normalise_timestamp

router = APIRouter(prefix="/api", tags=["activity"])

ActivityKind = Literal[
    "page_created",
    "page_edited",
    "suggestion",
    "ingest",
    "memory",
]

# Who caused the item to exist. Drives the accent edge in the stream: agent work
# is marked, your own work is not.
ActivityActor = Literal["you", "agent", "system"]


class ActivityItem(BaseModel):
    id: str
    kind: ActivityKind
    at: str
    title: str
    summary: str = ""
    actor: ActivityActor = "system"
    slug: str | None = None
    needs_review: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class ActivityFeed(BaseModel):
    items: list[ActivityItem]
    next_before: str | None = None
    pending_review: int = 0


def _parse_tags(raw: object) -> list[str]:
    """Tags live in a JSON text column; the stream wants a real list."""
    if isinstance(raw, list):
        return [str(tag) for tag in raw]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except ValueError:
            return []
        if isinstance(parsed, list):
            return [str(tag) for tag in parsed]
    return []


def _page_items(rows: list[dict[str, Any]]) -> list[ActivityItem]:
    items: list[ActivityItem] = []
    for row in rows:
        created = normalise_timestamp(row.get("created_at"))
        updated = normalise_timestamp(row.get("updated_at")) or created
        is_new = bool(created) and created == updated
        by_agent = (row.get("authored_by") or "user") == "agent"
        items.append(
            ActivityItem(
                id=f"page:{row['slug']}:{updated}",
                kind="page_created" if is_new else "page_edited",
                at=updated,
                title=row.get("title") or row["slug"],
                actor="agent" if by_agent else "you",
                slug=row["slug"],
                payload={"tags": _parse_tags(row.get("tags"))},
            )
        )
    return items


def _slug_from_target(target_id: str, wiki_id: str) -> str | None:
    """Page suggestions carry a `page:{wiki_id}:{slug}` target; others don't."""
    prefix = f"page:{wiki_id}:"
    return target_id[len(prefix) :] if target_id.startswith(prefix) else None


def _suggestion_items(suggestions: list[Any], wiki_id: str) -> list[ActivityItem]:
    items: list[ActivityItem] = []
    for s in suggestions:
        at = normalise_timestamp(s.updated_at) or normalise_timestamp(s.created_at)
        if not at:
            # Rows written before timestamps were exposed. Skipping keeps the
            # feed honestly ordered rather than pinning them to the epoch.
            continue
        target = s.target_id or ""
        items.append(
            ActivityItem(
                id=f"suggestion:{s.id}",
                kind="suggestion",
                at=at,
                title=s.proposed_markdown.strip().splitlines()[0][:140]
                if s.proposed_markdown.strip()
                else s.suggestion_type.replace("_", " "),
                summary=s.rationale,
                actor="agent",
                slug=_slug_from_target(target, wiki_id),
                needs_review=s.status == "pending",
                payload={
                    "suggestion_id": s.id,
                    "suggestion_type": s.suggestion_type,
                    "status": s.status,
                    "target_id": s.target_id,
                    "scopes": s.proposed_scopes,
                    "conflicts": s.conflicts,
                    "duplicates": s.duplicates,
                    "citations": s.citations,
                    "proposed_markdown": s.proposed_markdown,
                },
            )
        )
    return items


def _ingest_items(rows: list[dict[str, Any]]) -> list[ActivityItem]:
    items: list[ActivityItem] = []
    for row in rows:
        created = normalise_timestamp(row.get("created_at"))
        pages = (row.get("pages_created") or 0) + (row.get("pages_updated") or 0)
        items.append(
            ActivityItem(
                id=f"ingest:{row['id']}",
                kind="ingest",
                at=created,
                title=row.get("source_path") or row.get("source_type") or "Ingest",
                summary=row.get("error") or "",
                actor="you",
                payload={
                    "source_type": row.get("source_type"),
                    "status": row.get("status"),
                    "pages_created": row.get("pages_created") or 0,
                    "pages_updated": row.get("pages_updated") or 0,
                    "pages_touched": pages,
                },
            )
        )
    return items


def _memory_items(assets: list[Any]) -> list[ActivityItem]:
    items: list[ActivityItem] = []
    for asset in assets:
        at = normalise_timestamp(asset.updated_at) or normalise_timestamp(asset.created_at)
        if not at:
            continue
        items.append(
            ActivityItem(
                id=f"memory:{asset.id}:{asset.version}",
                kind="memory",
                at=at,
                title=asset.name or asset.summary[:140],
                summary=asset.summary,
                actor="system",
                slug=asset.page_slug,
                payload={
                    "asset_id": asset.id,
                    "layer": asset.layer,
                    "asset_type": asset.asset_type,
                    "status": asset.status,
                    "scope": asset.scope,
                    "disputed": bool(asset.conflict_lineage),
                },
            )
        )
    return items


@router.get("/activity", response_model=ActivityFeed)
async def get_activity(
    limit: int = Query(default=40, ge=1, le=200),
    before: str | None = Query(default=None),
    current_user: CurrentUser = Depends(get_current_user),
) -> ActivityFeed:
    """Merged, reverse-chronological feed of everything that happened."""
    wiki_id = current_user.wiki_id
    # Over-fetch each source so the merge has enough candidates to fill `limit`
    # even when one source dominates a time window.
    slice_size = min(limit * 2, 200)

    pages = await sqlite.list_recent_pages(wiki_id, limit=slice_size, before=before)
    ingests = await sqlite.list_ingest_logs(wiki_id, limit=slice_size)

    async with sqlite.get_db() as conn:
        repo = SuggestionRepository(conn)
        suggestions = await repo.list_suggestions(status=None)
        pending = [s for s in suggestions if s.status == "pending"]
        assets = await MemoryAssetRegistry(conn).list_assets(
            wiki_id=wiki_id, limit=slice_size
        )

    items = (
        _page_items(pages)
        + _suggestion_items(suggestions, wiki_id)
        + _ingest_items(ingests)
        + _memory_items(assets)
    )
    if before:
        items = [item for item in items if item.at and item.at < before]

    items.sort(key=lambda item: (item.at, item.id), reverse=True)
    window = items[:limit]
    next_before = window[-1].at if len(items) > limit and window else None

    return ActivityFeed(
        items=window,
        next_before=next_before,
        pending_review=len(pending),
    )
