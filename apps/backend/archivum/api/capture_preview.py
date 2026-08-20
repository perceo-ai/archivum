"""What Archivum thinks it will do with a capture, before you commit it.

The capture box shows its guess — kind, folder, links, tags — so filing is the
system's job rather than the user's. Two rules shape this endpoint:

1. It is deterministic and local. No model call, so it cannot be slow, cost
   anything, or fail in a way that blocks capture.
2. Every guess is grounded in the user's own vault: links are pages that
   actually exist, tags are tags they already use, folders are folders they
   already made. Nothing is invented.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from archivum.api.entries import KIND_VALUES, EntryKind
from archivum.auth import CurrentUser, get_current_user
from archivum.db import sqlite

router = APIRouter(prefix="/api/capture", tags=["capture"])

_URL_RE = re.compile(r"https?://\S+", re.I)
_QUESTION_RE = re.compile(r"\?\s*$")
_DECISION_RE = re.compile(
    r"\b(decided|decision|we(?:'ll| will)|going with|chose|choosing|ship(?:ping)? "
    r"the|settled on)\b",
    re.I,
)
_TASK_RE = re.compile(r"^\s*(todo|to-do|task)\b[:\-\s]", re.I)

# Folder names a vault commonly uses per kind, checked against folders that
# actually exist before being offered.
_KIND_FOLDER_HINTS: dict[str, tuple[str, ...]] = {
    "thought": ("inbox", "thoughts"),
    "decision": ("decisions",),
    "person": ("people",),
    "source": ("sources",),
    "conversation": ("sessions", "conversations"),
    "daily": ("daily", "journal"),
    "note": ("notes", "topics"),
}


class CapturePreviewRequest(BaseModel):
    text: str = ""


class ProposedLink(BaseModel):
    slug: str
    title: str


class CapturePreview(BaseModel):
    kind: EntryKind = "thought"
    folder: str = ""
    links: list[ProposedLink] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    # Plain-language explanation of the guess, shown under the capture box.
    reason: str = ""


def _existing_tags(rows: list[dict]) -> list[str]:
    seen: dict[str, int] = {}
    for row in rows:
        raw = row.get("tags")
        tags: list[str] = []
        if isinstance(raw, list):
            tags = [str(tag) for tag in raw]
        elif isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                tags = [str(tag) for tag in parsed] if isinstance(parsed, list) else []
            except ValueError:
                tags = []
        for tag in tags:
            key = tag.strip().lower()
            if key:
                seen[key] = seen.get(key, 0) + 1
    return sorted(seen, key=lambda tag: (-seen[tag], tag))


def _guess_kind(text: str) -> tuple[EntryKind, str]:
    stripped = text.strip()
    if not stripped:
        return "thought", ""
    if _URL_RE.search(stripped):
        return "source", "there's a link in it"
    if _TASK_RE.match(stripped):
        return "note", "it starts like a task"
    if _DECISION_RE.search(stripped):
        return "decision", "it reads like a decision"
    if _QUESTION_RE.search(stripped):
        return "thought", "it's a question"
    if len(stripped) > 600:
        return "note", "it's long enough to be a note"
    return "thought", "short and unstructured"


def _matching_pages(text: str, rows: list[dict], limit: int = 4) -> list[ProposedLink]:
    """Pages whose title appears verbatim in the captured text."""
    lowered = text.lower()
    matches: list[tuple[int, ProposedLink]] = []
    for row in rows:
        title = (row.get("title") or "").strip()
        # One- and two-character titles match everything; they are noise.
        if len(title) < 3:
            continue
        if re.search(rf"\b{re.escape(title.lower())}\b", lowered):
            matches.append(
                (len(title), ProposedLink(slug=row["slug"], title=title))
            )
    # Longest title first: the most specific match is the most useful link.
    matches.sort(key=lambda item: -item[0])
    return [link for _, link in matches[:limit]]


def _pick_folder(
    kind: str, links: list[ProposedLink], folders: set[str]
) -> tuple[str, str]:
    if links:
        folder = links[0].slug.rsplit("/", 1)[0] if "/" in links[0].slug else ""
        if folder:
            return folder, f"next to {links[0].title}"
    for hint in _KIND_FOLDER_HINTS.get(kind, ()):  # existing folders only
        for folder in sorted(folders):
            leaf = folder.rsplit("/", 1)[-1].lower()
            leaf = leaf.split(" ", 1)[-1] if " " in leaf else leaf
            if leaf == hint:
                return folder, f"where your other {hint} live"
    return "", "nothing obvious — it'll go to the vault root"


@router.post("/preview", response_model=CapturePreview)
async def preview_capture(
    body: CapturePreviewRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> CapturePreview:
    text = body.text or ""
    if not text.strip():
        return CapturePreview()

    rows = await sqlite.list_pages(current_user.wiki_id)
    folders = {
        row["slug"].rsplit("/", 1)[0] for row in rows if "/" in row["slug"]
    }

    kind, kind_reason = _guess_kind(text)
    links = _matching_pages(text, rows)
    folder, folder_reason = _pick_folder(kind, links, folders)

    lowered = text.lower()
    tags = [
        tag
        for tag in _existing_tags(rows)
        if re.search(rf"\b{re.escape(tag)}\b", lowered)
    ][:4]

    reason = kind_reason
    if folder_reason:
        reason = f"{kind_reason}; filing it {folder_reason}" if reason else folder_reason

    return CapturePreview(
        kind=kind,
        folder=folder,
        links=links,
        tags=tags,
        reason=reason,
    )
