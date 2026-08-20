"""Capture routes: record AI sessions (native turns or imported files) as Sources."""

from __future__ import annotations

import dataclasses
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

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
