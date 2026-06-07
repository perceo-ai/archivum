"""Ingest routes: /api/ingest/*

Supports file upload, URL ingest, and batch upload.
All ingest operations stream progress via SSE.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel

from archivum.auth import CurrentUser, decode_access_token, require_writer
from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.ingest.events import subscribe
from archivum.ingest.pipeline import ingest, ingest_batch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

MAX_BATCH_FILES = 20
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


def _safe_upload_name(filename: str | None) -> str:
    """Keep the client filename's basename without allowing path traversal."""
    name = Path(filename or "upload").name.strip()
    return name or "upload"


async def _save_upload_to_temp(file: UploadFile) -> tuple[Path, Path, str]:
    """Save an upload to a per-file temp dir while preserving its visible name."""
    original_name = _safe_upload_name(file.filename)
    tmp_dir = Path(tempfile.mkdtemp(prefix="archivum-upload-"))
    tmp_path = tmp_dir / original_name
    content = await file.read()
    tmp_path.write_bytes(content)
    return tmp_path, tmp_dir, original_name


# ── Routes ────────────────────────────────────────────────────────────────────

class URLIngestRequest(BaseModel):
    url: str


class IngestAcceptedResponse(BaseModel):
    accepted: bool
    file: str | None = None
    files: list[str] | None = None
    url: str | None = None


def _websocket_user(websocket: WebSocket, settings: Settings) -> CurrentUser | None:
    token = websocket.cookies.get("access_token")
    if not token:
        authorization = websocket.headers.get("authorization")
        if authorization and authorization.startswith("Bearer "):
            token = authorization[len("Bearer "):]
    if not token:
        return None

    try:
        payload = decode_access_token(token, settings)
    except HTTPException:
        return None

    if payload.role not in {"owner", "collaborator"}:
        return None
    return CurrentUser(username=payload.sub, role=payload.role, wiki_id=payload.wiki_id)


def _start_file_ingest_task(
    tmp_path: Path,
    tmp_dir: Path,
    original_name: str,
    wiki_id: str,
    settings: Settings,
) -> None:
    async def run() -> None:
        try:
            await ingest(tmp_path, wiki_id, settings=settings, source_name=original_name)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    asyncio.create_task(run())


def _start_url_ingest_task(url: str, wiki_id: str, settings: Settings) -> None:
    async def run() -> None:
        await ingest(url, wiki_id, settings=settings)

    asyncio.create_task(run())


def _start_batch_ingest_task(
    tmp_paths: list[Path],
    tmp_dirs: list[Path],
    original_names: list[str],
    wiki_id: str,
    settings: Settings,
) -> None:
    async def run() -> None:
        try:
            await ingest_batch(
                tmp_paths,
                wiki_id,
                settings=settings,
                source_names=original_names,
            )
        finally:
            for tmp_dir in tmp_dirs:
                shutil.rmtree(tmp_dir, ignore_errors=True)

    asyncio.create_task(run())


@router.post("/file")
async def ingest_file(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> IngestAcceptedResponse:
    """Upload a single file and start ingest. Progress is sent over /api/ingest/ws."""
    logger.info(
        "API ingest_file",
        extra={
            "upload_filename": file.filename,
            "content_type": file.content_type,
            "size": getattr(file, "size", None),
            "wiki_id": current_user.wiki_id,
        },
    )

    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={"detail": "File too large (max 50 MB)", "code": "file_too_large"},
        )

    # Save to a temp directory under the original basename. The pipeline still
    # reads the temp path, but logs/events/LLM source hints use original_name.
    tmp_path, tmp_dir, original_name = await _save_upload_to_temp(file)

    _start_file_ingest_task(tmp_path, tmp_dir, original_name, current_user.wiki_id, settings)
    return IngestAcceptedResponse(accepted=True, file=original_name)


@router.post("/url")
async def ingest_url(
    body: URLIngestRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> IngestAcceptedResponse:
    """Start URL ingest. Progress is sent over /api/ingest/ws."""
    logger.info("API ingest_url", extra={"wiki_id": current_user.wiki_id})

    url = body.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "URL must start with http:// or https://", "code": "invalid_url"},
        )

    _start_url_ingest_task(url, current_user.wiki_id, settings)
    return IngestAcceptedResponse(accepted=True, url=url)


@router.post("/batch")
async def ingest_batch_upload(
    files: list[UploadFile] = File(...),
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> IngestAcceptedResponse:
    """Upload up to 20 files and start batch ingest. Progress is sent over /api/ingest/ws."""
    logger.info(
        "API ingest_batch",
        extra={"files": len(files), "wiki_id": current_user.wiki_id},
    )

    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "detail": f"Maximum {MAX_BATCH_FILES} files per batch",
                "code": "too_many_files",
            },
        )

    # Save all files to per-file temp dirs under their original basenames.
    tmp_paths: list[Path] = []
    tmp_dirs: list[Path] = []
    original_names: list[str] = []
    for file in files:
        tmp_path, tmp_dir, original_name = await _save_upload_to_temp(file)
        tmp_paths.append(tmp_path)
        tmp_dirs.append(tmp_dir)
        original_names.append(original_name)

    _start_batch_ingest_task(
        tmp_paths,
        tmp_dirs,
        original_names,
        current_user.wiki_id,
        settings,
    )
    return IngestAcceptedResponse(accepted=True, files=original_names)


@router.get("/history")
async def ingest_history(
    limit: int = 50,
    current_user: CurrentUser = Depends(require_writer),
) -> list[dict]:
    """Return the ingest log for the current wiki."""
    logs = await sqlite.list_ingest_logs(current_user.wiki_id, limit=limit)
    return logs


@router.websocket("/ws")
async def ingest_websocket(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
) -> None:
    current_user = _websocket_user(websocket, settings)
    if current_user is None:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    logs = await sqlite.list_ingest_logs(current_user.wiki_id, limit=10)
    await websocket.send_json({"type": "snapshot", "logs": logs})

    async with subscribe(current_user.wiki_id) as queue:
        receive_task = asyncio.create_task(websocket.receive_json())
        event_task = asyncio.create_task(queue.get())
        try:
            while True:
                done, pending = await asyncio.wait(
                    {receive_task, event_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if receive_task in done:
                    try:
                        message = receive_task.result()
                    except WebSocketDisconnect:
                        break

                    if message.get("type") == "control" and message.get("action") == "ping":
                        await websocket.send_json({"type": "control_ack", "action": "ping"})
                    elif message.get("type") == "control":
                        await websocket.send_json(
                            {
                                "type": "control_error",
                                "action": message.get("action"),
                                "message": "Unsupported ingest control action",
                            }
                        )
                    receive_task = asyncio.create_task(websocket.receive_json())

                if event_task in done:
                    event = event_task.result()
                    await websocket.send_json({"type": "event", "event": event})
                    event_task = asyncio.create_task(queue.get())

                for task in pending:
                    if task.cancelled():
                        continue
        finally:
            receive_task.cancel()
            event_task.cancel()
