from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from archivum.auth import require_writer
from archivum.db import sqlite
from archivum.life_os.models import ProjectInput, TaskInput
from archivum.life_os.service import ensure_daily_note, register_project

router = APIRouter(prefix="/api/life", tags=["life-os"])


class DailyInput(BaseModel):
    date: str | None = None


@router.post("/daily")
async def create_daily_note(payload: DailyInput, _user=Depends(require_writer)):
    return await ensure_daily_note(payload.date, wiki_id="default")


@router.post("/projects")
async def create_project(payload: ProjectInput, _user=Depends(require_writer)):
    return await register_project(
        key=payload.key,
        name=payload.name,
        summary=payload.summary,
        status=payload.status,
        wiki_id="default",
    )


@router.get("/projects")
async def list_projects(_user=Depends(require_writer)):
    return await sqlite.list_life_projects("default")


@router.post("/tasks")
async def create_task(payload: TaskInput, _user=Depends(require_writer)):
    return await sqlite.create_life_task(
        wiki_id="default",
        title=payload.title,
        project_key=payload.project_key,
        page_slug=payload.page_slug,
        due_date=payload.due_date,
        source=payload.source,
    )


@router.get("/tasks")
async def list_tasks(status: str | None = None, _user=Depends(require_writer)):
    return await sqlite.list_life_tasks("default", status=status)
