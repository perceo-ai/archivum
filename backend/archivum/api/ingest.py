"""Ingest routes: /api/ingest/*

Supports file upload, URL ingest, and batch upload.
All ingest operations stream progress via SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from archivum.auth import CurrentUser, require_writer
from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.ingest.pipeline import ingest, ingest_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

MAX_BATCH_FILES = 20
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


# ── SSE helper ────────────────────────────────────────────────────────────────

async def _stream_ingest(
    source: str | Path,
    wiki_id: str,
    settings: Settings,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run ingest and yield SSE-compatible dicts."""
    queue: asyncio.Queue[dict | None] = asyncio.Queue()

    async def callback(event: dict) -> None:
        await queue.put(event)

    async def run():
        try:
            await ingest(source, wiki_id, callback, settings)
        finally:
            await queue.put(None)  # sentinel

    task = asyncio.create_task(run())

    while True:
        event = await queue.get()
        if event is None:
            break
        yield event

    await task


# ── Routes ────────────────────────────────────────────────────────────────────

class URLIngestRequest(BaseModel):
    url: str


@router.post("/file")
async def ingest_file(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """Upload a single file and stream ingest progress via SSE."""

    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"detail": "File too large (max 50 MB)", "code": "file_too_large"},
        )

    # Save to temp file
    suffix = Path(file.filename or "upload").suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    content = await file.read()
    tmp.write(content)
    tmp.flush()
    tmp.close()
    tmp_path = Path(tmp.name)

    async def event_generator():
        try:
            async for event in _stream_ingest(tmp_path, current_user.wiki_id, settings):
                yield {"data": json.dumps(event)}
        finally:
            tmp_path.unlink(missing_ok=True)

    return EventSourceResponse(event_generator())


@router.post("/url")
async def ingest_url(
    body: URLIngestRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """Ingest a URL and stream progress via SSE."""

    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "URL must start with http:// or https://", "code": "invalid_url"},
        )

    async def event_generator():
        async for event in _stream_ingest(url, current_user.wiki_id, settings):
            yield {"data": json.dumps(event)}

    return EventSourceResponse(event_generator())


@router.post("/batch")
async def ingest_batch_upload(
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    """Upload up to 20 files and stream batch progress via SSE."""

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": f"Maximum {MAX_BATCH_FILES} files per batch",
                "code": "too_many_files",
            },
        )

    # Save all files to temp
    tmp_paths: list[Path] = []
    for file in files:
        suffix = Path(file.filename or "upload").suffix
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        content = await file.read()
        tmp.write(content)
        tmp.flush()
        tmp.close()
        tmp_paths.append(Path(tmp.name))

    async def event_generator():
        queue: asyncio.Queue[dict | None] = asyncio.Queue()

        async def callback(event: dict) -> None:
            await queue.put(event)

        async def run():
            try:
                await ingest_batch(tmp_paths, current_user.wiki_id, callback, settings)
            finally:
                await queue.put(None)

        task = asyncio.create_task(run())

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield {"data": json.dumps(event)}
        finally:
            task.cancel()
            for p in tmp_paths:
                p.unlink(missing_ok=True)

    return EventSourceResponse(event_generator())


@router.get("/history")
async def ingest_history(
    limit: int = 50,
    current_user: CurrentUser = Depends(require_writer),
) -> list[dict]:
    """Return the ingest log for the current wiki."""
    logs = await sqlite.list_ingest_logs(current_user.wiki_id, limit=limit)
    return logs
