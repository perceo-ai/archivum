"""Capture routes: record AI sessions (native turns or imported files) as Sources."""

from __future__ import annotations

import dataclasses
import json
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from archivum.api.devices import require_device
from archivum.db import sqlite
from archivum.auth import CurrentUser, require_writer
from archivum.capture.importers import connector_for
from archivum.capture.importers import chatgpt as _chatgpt  # noqa: F401 (self-register)
from archivum.capture.importers import claude_code as _cc  # noqa: F401 (self-register)
from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.capture.store import CaptureResult, CaptureStore
from archivum.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["capture"])


class ToolCallModel(BaseModel):
    name: str
    arguments: dict = {}
    result: str | None = None
    call_id: str | None = None
    ok: bool = True


class TurnModel(BaseModel):
    role: str
    text: str = ""
    ts: str = ""
    tool_calls: list[ToolCallModel] = []


class CaptureConversationRequest(BaseModel):
    session_id: str
    interface: str = "claude_code_native"
    started_at: str = ""
    turns: list[TurnModel] = []
    scope: str = "personal"
    origin_uri: str = ""


class CaptureImportRequest(BaseModel):
    path: str
    scope: str = "personal"


class CaptureResponse(BaseModel):
    source_id: str
    content_hash: str
    version: int
    document_id: str
    chunk_count: int
    deduplicated: bool


class CaptureImportResponse(BaseModel):
    interface: str
    results: list[CaptureResponse]


def _to_response(res: CaptureResult) -> CaptureResponse:
    return CaptureResponse(
        source_id=res.source_id, content_hash=res.content_hash, version=res.version,
        document_id=res.document_id, chunk_count=len(res.chunk_ids),
        deduplicated=res.deduplicated,
    )


def _build_conversation(body: CaptureConversationRequest) -> Conversation:
    turns = tuple(
        Turn(
            role=t.role, text=t.text, ts=t.ts,  # type: ignore[arg-type]
            tool_calls=tuple(
                ToolCall(name=c.name, arguments=c.arguments, result=c.result,
                         call_id=c.call_id, ok=c.ok)
                for c in t.tool_calls
            ),
        )
        for t in body.turns
    )
    return Conversation(
        session_id=body.session_id, interface=body.interface,
        started_at=body.started_at, turns=turns, scope=body.scope,
        origin_uri=body.origin_uri,
    )


@router.post("/capture", response_model=CaptureResponse)
async def capture_endpoint(
    body: CaptureConversationRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> CaptureResponse:
    store = CaptureStore(wiki_id=current_user.wiki_id, settings=settings)
    res = await store.capture(_build_conversation(body))
    # Distillation may call a model, so it happens on the queue. Capture stays
    # instant and works whether or not a model is reachable.
    await sqlite.enqueue_distillation(res.source_id, current_user.wiki_id)
    return _to_response(res)


@router.post("/capture/import", response_model=CaptureImportResponse)
async def capture_import_endpoint(
    body: CaptureImportRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> CaptureImportResponse:
    path = Path(body.path)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"cannot read {body.path}", "code": "unreadable_source"},
        )
    connector = connector_for(path)
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"no importer for {body.path}", "code": "no_importer"},
        )
    store = CaptureStore(wiki_id=current_user.wiki_id, settings=settings)
    try:
        result = connector.parse(path)
    except (json.JSONDecodeError, ValueError, OSError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"cannot parse {body.path}", "code": "unparseable_source"},
        )
    responses: list[CaptureResponse] = []
    for conv in result.conversations:
        scoped = conv if body.scope == "personal" else _rescope(conv, body.scope)
        responses.append(_to_response(await store.capture(scoped)))
    return CaptureImportResponse(interface=result.interface, results=responses)


def _rescope(conv: Conversation, scope: str) -> Conversation:
    return dataclasses.replace(conv, scope=scope)


@router.post("/capture/upload", response_model=CaptureImportResponse)
async def capture_upload_endpoint(
    transcript: UploadFile = File(...),
    filename: str = Form(""),
    scope: str = Form("personal"),
    device: dict = Depends(require_device),
    settings: Settings = Depends(get_settings),
) -> CaptureImportResponse:
    """Capture a transcript from a machine the server cannot read.

    `/capture/import` resolves a path on the server, which is correct for a
    file already there and impossible for a laptop's `~/.claude/projects`. The
    bytes come over the wire instead and meet the same importers, so there is
    one parser rather than one per client language.

    Authenticated by device key: the caller is a linked machine running the
    watcher, not a browser session.
    """
    # The importer chooses on extension, so the original name has to survive
    # the upload — a temp file called `tmpXXXX` matches no connector.
    suffix = Path(filename or transcript.filename or "transcript.jsonl").suffix or ".jsonl"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as staged:
        staged_path = Path(staged.name)
        while chunk := await transcript.read(1024 * 1024):
            staged.write(chunk)

    try:
        connector = connector_for(staged_path)
        if connector is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": f"no importer for {suffix}", "code": "no_importer"},
            )
        try:
            result = connector.parse(staged_path)
        except (json.JSONDecodeError, ValueError, OSError):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": "cannot parse transcript", "code": "unparseable_source"},
            )

        store = CaptureStore(wiki_id=device["wiki_id"], settings=settings)
        responses: list[CaptureResponse] = []
        for conv in result.conversations:
            scoped = conv if scope == "personal" else _rescope(conv, scope)
            captured = await store.capture(scoped)
            # Capture is content-addressed, so re-uploading an unchanged
            # transcript is a no-op rather than a duplicate. That is what lets
            # the watcher be simple and re-send when unsure.
            if not captured.deduplicated:
                await sqlite.enqueue_distillation(captured.source_id, device["wiki_id"])
            responses.append(_to_response(captured))
        return CaptureImportResponse(interface=result.interface, results=responses)
    finally:
        staged_path.unlink(missing_ok=True)
