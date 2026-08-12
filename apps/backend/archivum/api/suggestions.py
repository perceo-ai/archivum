"""Human review lifecycle routes for agent-proposed memory suggestions."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from archivum.api.pages import _validate_slug
from archivum.auth import CurrentUser, get_current_user, require_writer
from archivum.db import sqlite
from archivum.knowledge.suggestions import (
    MemorySuggestion,
    SuggestionRepository,
    SuggestionStatus,
)

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


class CreateSuggestionRequest(BaseModel):
    target_id: str | None = None
    page_slug: str | None = None
    suggestion_type: str = Field(min_length=1)
    proposed_markdown: str = ""
    proposed_objects: list[Any] = Field(default_factory=list)
    citations: list[Any] = Field(default_factory=list)

    @model_validator(mode="after")
    def target_is_unambiguous(self) -> "CreateSuggestionRequest":
        if bool(self.target_id) == bool(self.page_slug):
            raise ValueError("Provide exactly one of target_id or page_slug")
        return self


@router.get("", response_model=list[MemorySuggestion])
async def list_suggestions(
    page_slug: str | None = Query(default=None),
    status_filter: SuggestionStatus | None = Query(default="pending", alias="status"),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[MemorySuggestion]:
    """List pending review suggestions visible to the authenticated wiki."""
    async with sqlite.get_db() as conn:
        repo = SuggestionRepository(conn)
        if page_slug is not None:
            target_id = _page_target_id(current_user.wiki_id, page_slug)
            return await repo.list_suggestions(target_id=target_id, status=status_filter)
        return await repo.list_suggestions(
            target_ids=[_wiki_target_id(current_user.wiki_id)],
            target_prefixes=[
                _page_target_prefix(current_user.wiki_id),
                _wiki_target_prefix(current_user.wiki_id),
            ],
            status=status_filter,
        )


@router.post("", response_model=MemorySuggestion, status_code=status.HTTP_201_CREATED)
async def create_suggestion(
    body: CreateSuggestionRequest,
    current_user: CurrentUser = Depends(require_writer),
) -> MemorySuggestion:
    """Create a wiki-scoped suggestion for internal authenticated callers."""
    target_id = (
        _page_target_id(current_user.wiki_id, body.page_slug)
        if body.page_slug is not None
        else body.target_id
    )
    assert target_id is not None
    _require_authorized_target(target_id, current_user.wiki_id)
    async with sqlite.get_db() as conn:
        return await SuggestionRepository(conn).create_suggestion(
            target_id=target_id,
            suggestion_type=body.suggestion_type,
            proposed_markdown=body.proposed_markdown,
            proposed_objects=body.proposed_objects,
            citations=body.citations,
        )


@router.post("/{suggestion_id:path}/accept", response_model=MemorySuggestion)
async def accept_suggestion(
    suggestion_id: str,
    current_user: CurrentUser = Depends(require_writer),
) -> MemorySuggestion:
    return await _transition_suggestion(suggestion_id, "accepted", current_user)


@router.post("/{suggestion_id:path}/reject", response_model=MemorySuggestion)
async def reject_suggestion(
    suggestion_id: str,
    current_user: CurrentUser = Depends(require_writer),
) -> MemorySuggestion:
    return await _transition_suggestion(suggestion_id, "rejected", current_user)


async def _transition_suggestion(
    suggestion_id: str,
    target_status: SuggestionStatus,
    current_user: CurrentUser,
) -> MemorySuggestion:
    async with sqlite.get_db() as conn:
        repo = SuggestionRepository(conn)
        suggestion = await repo.get_suggestion(suggestion_id)
        if suggestion is None or not _is_authorized_target(
            suggestion.target_id, current_user.wiki_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "Suggestion not found", "code": "suggestion_not_found"},
            )
        try:
            if target_status == "accepted":
                await repo.accept_suggestion(suggestion_id)
            else:
                await repo.reject_suggestion(suggestion_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"detail": str(exc), "code": "suggestion_conflict"},
            ) from exc
        loaded = await repo.get_suggestion(suggestion_id)
        assert loaded is not None
        return loaded


def _page_target_id(wiki_id: str, slug: str) -> str:
    return f"{_page_target_prefix(wiki_id)}{_validate_slug(slug)}"


def _page_target_prefix(wiki_id: str) -> str:
    return f"page:{wiki_id}:"


def _wiki_target_id(wiki_id: str) -> str:
    return f"wiki:{wiki_id}"


def _wiki_target_prefix(wiki_id: str) -> str:
    return f"wiki:{wiki_id}:"


def _is_authorized_target(target_id: str, wiki_id: str) -> bool:
    return (
        target_id == _wiki_target_id(wiki_id)
        or target_id.startswith(_wiki_target_prefix(wiki_id))
        or target_id.startswith(_page_target_prefix(wiki_id))
    )


def _require_authorized_target(target_id: str, wiki_id: str) -> None:
    if not _is_authorized_target(target_id, wiki_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "detail": "Suggestion target is not authorized for this wiki",
                "code": "unauthorized_suggestion_target",
            },
        )
