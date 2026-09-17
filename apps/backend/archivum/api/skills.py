"""Skills that follow you to every machine.

A skill is a repeatable procedure — the thing you would otherwise re-explain at
the start of every session. They live in `~/.claude/skills/` on one laptop,
which is exactly the problem `CLAUDE.md` has and the reason this product
exists: per-machine, tied to a checkout, invisible from anywhere else.

Stored as ordinary vault pages under `skills/`, so a synced skill is markdown on
disk, editable in the browser, and versioned like every other page. Inventing a
second store for them would mean a second thing to back up, index, and explain.

Device-authenticated rather than owner-authenticated: the caller is a linked
machine running `archivum skills pull`, not a browser session.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from archivum.api.devices import require_device
from archivum.config import Settings, get_settings
from archivum.db import sqlite

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/skills", tags=["skills"])

SKILL_PREFIX = "skills/"

# A skill name becomes a page slug under `skills/`. Anything with a separator
# in it would write outside that folder, so names are a flat, boring alphabet
# rather than a path that is sanitised into one.
_VALID_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class PushSkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    content: str = Field(min_length=1)


def _slug_for(name: str) -> str:
    if not _VALID_NAME.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": (
                    f"'{name}' is not a usable skill name. Use lowercase letters, "
                    "digits and hyphens — it becomes a page under skills/."
                ),
                "code": "invalid_skill_name",
            },
        )
    return f"{SKILL_PREFIX}{name}"


async def write_skill(*, name: str, content: str, wiki_id: str) -> dict[str, Any]:
    """Persist one skill as a vault page, replacing any previous version."""
    from archivum.page_write_queue import apply_page_write

    settings: Settings = get_settings()
    return await apply_page_write(
        title=name,
        content=content,
        slug=_slug_for(name),
        tags=["skill"],
        authored_by="agent",
        wiki_id=wiki_id,
        settings=settings,
    )


async def list_skills(*, wiki_id: str) -> list[dict[str, Any]]:
    rows = await sqlite.list_pages(wiki_id)
    return [
        {
            "name": row["slug"][len(SKILL_PREFIX):],
            "updated_at": row["updated_at"],
        }
        for row in rows
        if row["slug"].startswith(SKILL_PREFIX)
    ]


async def read_skill(name: str, *, wiki_id: str) -> dict[str, Any] | None:
    row = await sqlite.get_page(_slug_for(name), wiki_id)
    return dict(row) if row else None


@router.post("")
async def push_skill(
    body: PushSkillRequest,
    device: dict[str, Any] = Depends(require_device),
) -> dict[str, Any]:
    """Store a skill from this machine, so every other machine can have it."""
    row = await write_skill(
        name=body.name, content=body.content, wiki_id=device["wiki_id"]
    )
    logger.info("Skill pushed", extra={"skill": body.name, "wiki_id": device["wiki_id"]})
    return {"name": body.name, "slug": row.get("slug", _slug_for(body.name))}


@router.get("")
async def get_skills(
    device: dict[str, Any] = Depends(require_device),
) -> dict[str, Any]:
    return {"skills": await list_skills(wiki_id=device["wiki_id"])}


@router.get("/{name}")
async def get_skill(
    name: str,
    device: dict[str, Any] = Depends(require_device),
) -> dict[str, Any]:
    row = await read_skill(name, wiki_id=device["wiki_id"])
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": f"No skill named '{name}'", "code": "skill_not_found"},
        )
    return {"name": name, "content": row["content"], "updated_at": row["updated_at"]}
