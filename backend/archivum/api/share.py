"""Share routes.

- /api/share/*        — public read-only viewer (no auth required)
- /api/share-links/*  — authenticated management (create / list / revoke)
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from archivum.auth import CurrentUser, require_writer
from archivum.db import sqlite

router = APIRouter(prefix="/api/share", tags=["share"])
mgmt_router = APIRouter(prefix="/api/share-links", tags=["share-links"])
logger = logging.getLogger(__name__)


# ── Schemas ───────────────────────────────────────────────────────────────────

class SharePageResponse(BaseModel):
    type: str
    token: str
    wiki_id: str

    # page type
    slug: str | None = None
    title: str | None = None
    tags: list[str] = []
    content: str | None = None

    # query type
    question: str | None = None
    answer: str | None = None
    citations: list[dict[str, str]] = []

    # diagnostics
    expires_at: str | None = None


class CreateShareLinkRequest(BaseModel):
    type: str = "page"
    target_id: str | None = None
    question: str | None = None
    answer: str | None = None
    citations: list[dict[str, str]] = []
    expires_in_days: int | None = None


class CreateShareLinkResponse(BaseModel):
    token: str
    url: str
    expires_at: str | None = None


class ShareLinkInfo(BaseModel):
    id: int
    wiki_id: str
    token: str
    type: str
    target_id: str | None = None
    created_at: str
    expires_at: str | None = None
    revoked: int


# ── Helpers ───────────────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{10,}$")


def _deserialize_tags(tags_raw: object) -> list[str]:
    if isinstance(tags_raw, list):
        return [str(t) for t in tags_raw]
    if tags_raw is None:
        return []
    if isinstance(tags_raw, str):
        try:
            parsed = json.loads(tags_raw)
            if isinstance(parsed, list):
                return [str(t) for t in parsed]
        except json.JSONDecodeError:
            return []
    return []


def _is_expired(expires_at: str | None) -> bool:
    if not expires_at:
        return False
    try:
        # Allow both ISO and sqlite datetime strings.
        exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        return exp <= datetime.now(UTC)
    except Exception:
        return False


def _query_payload_from_target(target_id: object) -> dict[str, object] | None:
    if not isinstance(target_id, str):
        return None
    try:
        payload = json.loads(target_id)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


# ── Public read route ─────────────────────────────────────────────────────────

@router.get("/{token}", response_model=SharePageResponse)
async def get_share(token: str) -> SharePageResponse:
    if not _TOKEN_RE.match(token):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Invalid share token", "code": "invalid_token"},
        )

    link = await sqlite.get_share_link(token)
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Share link not found", "code": "share_not_found"},
        )

    if link.get("expires_at") and _is_expired(link.get("expires_at")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Share link expired", "code": "share_expired"},
        )

    link_type = str(link.get("type") or "page")
    if link_type == "query":
        payload = _query_payload_from_target(link.get("target_id"))
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "Shared query not found", "code": "shared_query_missing"},
            )
        citations_raw = payload.get("citations")
        citations: list[dict[str, str]] = []
        if isinstance(citations_raw, list):
            for item in citations_raw:
                if isinstance(item, dict):
                    slug = str(item.get("slug") or "")
                    title = str(item.get("title") or slug)
                    if slug:
                        citations.append({"slug": slug, "title": title})

        return SharePageResponse(
            type=link_type,
            token=token,
            wiki_id=str(link.get("wiki_id") or "default"),
            title=str(payload.get("question") or "Shared query"),
            question=str(payload.get("question") or ""),
            answer=str(payload.get("answer") or ""),
            citations=citations,
            expires_at=link.get("expires_at"),
        )

    if link_type != "page":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"Unsupported share type '{link_type}'", "code": "unsupported_share_type"},
        )

    slug = link.get("target_id")
    if not slug or not isinstance(slug, str):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Share target missing", "code": "share_target_missing"},
        )

    page = await sqlite.get_page(slug, link.get("wiki_id") or "default")
    if not page:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "Shared page not found", "code": "shared_page_not_found"},
        )

    return SharePageResponse(
        type=link_type,
        token=token,
        wiki_id=str(link.get("wiki_id") or "default"),
        slug=page.get("slug"),
        title=page.get("title"),
        content=page.get("content"),
        tags=_deserialize_tags(page.get("tags")),
        expires_at=link.get("expires_at"),
    )


# ── Authenticated management routes ──────────────────────────────────────────

@mgmt_router.post("", response_model=CreateShareLinkResponse, status_code=status.HTTP_201_CREATED)
async def create_share_link(
    body: CreateShareLinkRequest,
    current_user: CurrentUser = Depends(require_writer),
) -> CreateShareLinkResponse:
    link_type = body.type.strip().lower()
    if link_type not in {"page", "query"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Share type must be 'page' or 'query'", "code": "invalid_share_type"},
        )

    target_id = body.target_id
    if link_type == "page":
        if not target_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": "Page share requires target_id", "code": "missing_target"},
            )
        page = await sqlite.get_page(target_id, current_user.wiki_id)
        if not page:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "Page not found", "code": "page_not_found"},
            )
    else:
        question = (body.question or "").strip()
        answer = (body.answer or "").strip()
        if not question or not answer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"detail": "Query share requires question and answer", "code": "missing_query_payload"},
            )
        citations: list[dict[str, str]] = []
        for item in body.citations:
            slug = str(item.get("slug") or "")
            title = str(item.get("title") or slug)
            if slug:
                citations.append({"slug": slug, "title": title})
        target_id = json.dumps(
            {"question": question, "answer": answer, "citations": citations},
            separators=(",", ":"),
        )

    token = secrets.token_urlsafe(32)

    expires_at: str | None = None
    if body.expires_in_days is not None:
        exp_dt = datetime.now(UTC) + timedelta(days=body.expires_in_days)
        expires_at = exp_dt.isoformat()

    await sqlite.create_share_link(
        token=token,
        link_type=link_type,
        target_id=target_id,
        expires_at=expires_at,
        wiki_id=current_user.wiki_id,
    )

    return CreateShareLinkResponse(
        token=token,
        url=f"/share/{token}",
        expires_at=expires_at,
    )


@mgmt_router.get("", response_model=list[ShareLinkInfo])
async def list_share_links(
    current_user: CurrentUser = Depends(require_writer),
) -> list[ShareLinkInfo]:
    rows = await sqlite.list_share_links(wiki_id=current_user.wiki_id)
    return [ShareLinkInfo(**row) for row in rows]


@mgmt_router.delete("/{token}")
async def revoke_share_link(
    token: str,
    current_user: CurrentUser = Depends(require_writer),
) -> dict[str, str]:
    revoked = await sqlite.revoke_share_link(token)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )
    return {"detail": "revoked"}
