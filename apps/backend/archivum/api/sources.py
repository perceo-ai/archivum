"""Sources routes: /api/sources/* — deterministic ingestion + read-back."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from archivum.auth import CurrentUser, require_writer
from archivum.config import Settings, get_settings
from archivum.store.ingest import ingest_source
from archivum.store.models import IngestResult, Source
from archivum.store.repository import SourceStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceIngestRequest(BaseModel):
    origin_uri: str
    scope: str = "personal"
    source_type: str | None = None


class SourceResponse(BaseModel):
    id: str
    content_hash: str
    version: int
    source_type: str
    origin_uri: str
    scope: str
    deduplicated: bool
    chunk_count: int


class SourceDetailResponse(BaseModel):
    source: SourceResponse
    chunk_count: int


async def _read_bytes(origin_uri: str) -> bytes:
    """Fetch the raw bytes for an origin (local file path/URI or http(s))."""
    parsed = urlparse(origin_uri)
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(origin_uri)
            resp.raise_for_status()
            return resp.content
    path = Path(parsed.path if parsed.scheme == "file" else origin_uri)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"cannot read source: {origin_uri}", "code": "unreadable_source"},
        )
    return path.read_bytes()


def _to_response(result: IngestResult) -> SourceResponse:
    return SourceResponse(
        id=result.source.id,
        content_hash=result.source.content_hash,
        version=result.source.version,
        source_type=result.source.source_type.value,
        origin_uri=result.source.origin_uri,
        scope=result.source.scope,
        deduplicated=result.deduplicated,
        chunk_count=len(result.chunks),
    )


@router.post("/ingest", response_model=SourceResponse)
async def ingest_endpoint(
    body: SourceIngestRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> SourceResponse:
    logger.info("API sources.ingest", extra={"origin_uri": body.origin_uri})
    raw_bytes = await _read_bytes(body.origin_uri)
    result = await ingest_source(
        origin_uri=body.origin_uri,
        raw_bytes=raw_bytes,
        scope=body.scope,
        explicit_type=body.source_type,
        settings=settings,
    )
    return _to_response(result)


@router.get("/{source_id}", response_model=SourceDetailResponse)
async def get_source_endpoint(
    source_id: str,
    current_user: CurrentUser = Depends(require_writer),
) -> SourceDetailResponse:
    store = SourceStore()
    source: Source | None = await store.get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "source not found", "code": "source_not_found"},
        )
    document = await store.get_document_for_source(source.id)
    chunk_count = len(await store.list_chunks(document.id)) if document else 0
    return SourceDetailResponse(
        source=SourceResponse(
            id=source.id,
            content_hash=source.content_hash,
            version=source.version,
            source_type=source.source_type.value,
            origin_uri=source.origin_uri,
            scope=source.scope,
            deduplicated=False,
            chunk_count=chunk_count,
        ),
        chunk_count=chunk_count,
    )
