"""One list of everything, with a computed kind.

The memory system keeps pages, sources, and governed assets in separate stores
for good reasons — different lifecycles, different provenance rules. But a
person browsing their own vault does not think in stores; they think "show me
everything, filter it by what kind of thing it is."

This module is a *view*. It composes the existing stores and computes a `kind`
per row. It owns no storage and changes no memory semantics.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from archivum.auth import CurrentUser, get_current_user
from archivum.db import sqlite
from archivum.knowledge.suggestions import SuggestionRepository, wiki_scope
from archivum.store.repository import SourceStore
from archivum.timestamps import normalise_timestamp

router = APIRouter(prefix="/api", tags=["entries"])

EntryKind = Literal[
    "note",
    "thought",
    "source",
    "conversation",
    "person",
    "decision",
    "daily",
]

KIND_VALUES: tuple[EntryKind, ...] = (
    "note",
    "thought",
    "source",
    "conversation",
    "person",
    "decision",
    "daily",
)

# A page's kind comes from the user's own filing, never from guesswork:
# an explicit tag wins, then the folder they put it in, then plain "note".
_TAG_KINDS = {kind: kind for kind in KIND_VALUES}
_TAG_KINDS.update({f"type/{kind}": kind for kind in KIND_VALUES})

_FOLDER_KINDS: dict[str, EntryKind] = {
    "people": "person",
    "person": "person",
    "decisions": "decision",
    "decision": "decision",
    "daily": "daily",
    "journal": "daily",
    "thoughts": "thought",
    "inbox": "thought",
    "sources": "source",
    "conversations": "conversation",
    "sessions": "conversation",
}

# Store source types collapse into the two kinds a person distinguishes.
_SOURCE_TYPE_KINDS: dict[str, EntryKind] = {
    "conversation": "conversation",
    "message": "conversation",
}


class Entry(BaseModel):
    id: str
    kind: EntryKind
    title: str
    slug: str | None = None
    folder: str = ""
    updated_at: str = ""
    created_at: str = ""
    actor: Literal["you", "agent"] = "you"
    needs_review: bool = False
    tags: list[str] = Field(default_factory=list)
    detail: str = ""


class EntryList(BaseModel):
    entries: list[Entry]
    counts: dict[str, int] = Field(default_factory=dict)
    total: int = 0


def _page_kind(slug: str, tags: list[str]) -> EntryKind:
    for tag in tags:
        kind = _TAG_KINDS.get(tag.strip().lower())
        if kind:
            return kind  # type: ignore[return-value]
    head = slug.split("/", 1)[0].strip().lower()
    # Tolerate numeric ordering prefixes like "40 People" without requiring them.
    head = head.split(" ", 1)[-1] if " " in head else head
    return _FOLDER_KINDS.get(head, "note")


def _folder_of(slug: str) -> str:
    return slug.rsplit("/", 1)[0] if "/" in slug else ""


def _parse_tags(raw: object) -> list[str]:
    if isinstance(raw, list):
        return [str(tag) for tag in raw]
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            parsed = json.loads(raw)
        except ValueError:
            return [part for part in raw.split(",") if part.strip()]
        if isinstance(parsed, list):
            return [str(tag) for tag in parsed]
    return []


@router.get("/entries", response_model=EntryList)
async def list_entries(
    kind: str | None = Query(default=None),
    needs_review: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=1000),
    current_user: CurrentUser = Depends(get_current_user),
) -> EntryList:
    """Pages and sources as one list, each tagged with the kind of thing it is."""
    wiki_id = current_user.wiki_id

    pages = await sqlite.list_pages(wiki_id)

    async with sqlite.get_db() as conn:
        pending = await SuggestionRepository(conn).list_suggestions(
            status="pending", **wiki_scope(wiki_id)
        )
    sources = await SourceStore().list_sources(wiki_id=wiki_id, limit=limit)

    page_prefix = f"page:{wiki_id}:"
    awaiting = {
        s.target_id[len(page_prefix) :]
        for s in pending
        if s.target_id.startswith(page_prefix)
    }

    entries: list[Entry] = []
    for row in pages:
        slug = row["slug"]
        tags = _parse_tags(row.get("tags"))
        entries.append(
            Entry(
                id=f"page:{slug}",
                kind=_page_kind(slug, tags),
                title=row.get("title") or slug,
                slug=slug,
                folder=_folder_of(slug),
                updated_at=normalise_timestamp(row.get("updated_at")),
                created_at=normalise_timestamp(row.get("created_at")),
                actor="agent" if row.get("authored_by") == "agent" else "you",
                needs_review=slug in awaiting,
                tags=tags,
            )
        )

    for source in sources:
        entries.append(
            Entry(
                id=f"source:{source.id}",
                kind=_SOURCE_TYPE_KINDS.get(source.source_type.value, "source"),
                title=source.origin_uri.rsplit("/", 1)[-1] or source.origin_uri,
                folder="",
                updated_at=normalise_timestamp(source.ingested_at),
                created_at=normalise_timestamp(source.ingested_at),
                detail=source.origin_uri,
            )
        )

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.kind] = counts.get(entry.kind, 0) + 1

    total = len(entries)
    if kind:
        entries = [entry for entry in entries if entry.kind == kind]
    if needs_review:
        entries = [entry for entry in entries if entry.needs_review]

    entries.sort(key=lambda entry: (entry.updated_at, entry.id), reverse=True)
    return EntryList(entries=entries[:limit], counts=counts, total=total)
