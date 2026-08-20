"""Routes that start a structured note for you.

The project and task *listing* routes are gone with the life_* tables: those
nouns are pages, and /api/entries lists them with everything else rather than
maintaining a second, weaker model of the same thing.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from archivum.auth import CurrentUser, require_writer
from archivum.config import Settings, get_settings
from archivum.life_os.service import ensure_daily_note, register_project

router = APIRouter(prefix="/api/life", tags=["life-os"])


class DailyInput(BaseModel):
    date: str | None = None


class ProjectInput(BaseModel):
    key: str
    name: str
    summary: str = ""
    status: str = "active"


@router.post("/daily")
async def create_daily_note(
    payload: DailyInput,
    user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
):
    return await ensure_daily_note(payload.date, wiki_id=user.wiki_id, settings=settings)


@router.post("/projects")
async def create_project(
    payload: ProjectInput,
    user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
):
    return await register_project(
        key=payload.key,
        name=payload.name,
        summary=payload.summary,
        status=payload.status,
        wiki_id=user.wiki_id,
        settings=settings,
    )
