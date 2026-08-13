"""Human review lifecycle routes for agent-proposed memory suggestions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, model_validator

from archivum.api.pages import _validate_slug
from archivum.auth import CurrentUser, get_current_user, require_writer
from archivum.db import sqlite
from archivum.knowledge.models import Citation
from archivum.knowledge.suggestions import (
    MemorySuggestion,
    SuggestionAction,
    SuggestionRepository,
    SuggestionStatus,
)
from archivum.memory.registry import MemoryAssetRegistry

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])


class CreateSuggestionRequest(BaseModel):
    target_id: str | None = None
    page_slug: str | None = None
    suggestion_type: str = Field(min_length=1)
    proposed_markdown: str = ""
    proposed_objects: list[Any] = Field(default_factory=list)
    citations: list[Any] = Field(default_factory=list)
    proposed_scopes: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    duplicates: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    retention_tier: str = "candidate"
    agent_visibility: str = "review_required"
    rationale: str = ""
    estimated_durability: str = ""
    expires_at: str | None = None

    @model_validator(mode="after")
    def target_is_unambiguous(self) -> "CreateSuggestionRequest":
        if bool(self.target_id) == bool(self.page_slug):
            raise ValueError("Provide exactly one of target_id or page_slug")
        return self


class ReviewSuggestionRequest(BaseModel):
    action: SuggestionAction
    asset_id: str | None = None
    scope: str | None = None
    visibility: str | None = None


class ExpireSuggestionsRequest(BaseModel):
    now: str = Field(min_length=1)


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
            proposed_scopes=body.proposed_scopes,
            scores=body.scores,
            duplicates=body.duplicates,
            conflicts=body.conflicts,
            retention_tier=body.retention_tier,
            agent_visibility=body.agent_visibility,
            rationale=body.rationale,
            estimated_durability=body.estimated_durability,
            expires_at=body.expires_at,
        )


@router.post("/expire", response_model=list[MemorySuggestion])
async def expire_suggestions(
    body: ExpireSuggestionsRequest,
    current_user: CurrentUser = Depends(require_writer),
) -> list[MemorySuggestion]:
    async with sqlite.get_db() as conn:
        repo = SuggestionRepository(conn)
        expired = await repo.expire_due_candidates(body.now)
        return [
            suggestion
            for suggestion in expired
            if _is_authorized_target(suggestion.target_id, current_user.wiki_id)
        ]


@router.post("/{suggestion_id:path}/accept", response_model=MemorySuggestion)
async def accept_suggestion(
    suggestion_id: str,
    current_user: CurrentUser = Depends(require_writer),
) -> MemorySuggestion:
    return await _review_suggestion(
        suggestion_id,
        ReviewSuggestionRequest(action="accept"),
        current_user,
    )


@router.post("/{suggestion_id:path}/reject", response_model=MemorySuggestion)
async def reject_suggestion(
    suggestion_id: str,
    current_user: CurrentUser = Depends(require_writer),
) -> MemorySuggestion:
    return await _review_suggestion(
        suggestion_id,
        ReviewSuggestionRequest(action="reject"),
        current_user,
    )


@router.post("/{suggestion_id:path}/review", response_model=MemorySuggestion)
async def review_suggestion(
    suggestion_id: str,
    body: ReviewSuggestionRequest,
    current_user: CurrentUser = Depends(require_writer),
) -> MemorySuggestion:
    return await _review_suggestion(suggestion_id, body, current_user)


async def _review_suggestion(
    suggestion_id: str,
    body: ReviewSuggestionRequest,
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
            if suggestion.status != "pending":
                raise ValueError(
                    f"Suggestion '{suggestion_id}' is not pending and cannot be transitioned"
                )
            await _apply_review_effect(conn, suggestion, body, current_user)
            await repo.transition_suggestion(suggestion_id, body.action)
        except ValueError as exc:
            conflict = "is not pending" in str(exc)
            error_status = (
                status.HTTP_409_CONFLICT
                if conflict
                else status.HTTP_400_BAD_REQUEST
            )
            raise HTTPException(
                status_code=error_status,
                detail={
                    "detail": str(exc),
                    "code": "suggestion_conflict" if conflict else "invalid_review_action",
                },
            ) from exc
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": str(exc), "code": "review_target_not_found"},
            ) from exc
        loaded = await repo.get_suggestion(suggestion_id)
        assert loaded is not None
        return loaded


async def _apply_review_effect(
    conn: Any,
    suggestion: MemorySuggestion,
    body: ReviewSuggestionRequest,
    current_user: CurrentUser,
) -> None:
    registry = MemoryAssetRegistry(conn)
    if body.action in {"accept", "merge", "keep_both"}:
        await _register_suggestion_asset(
            registry,
            suggestion,
            current_user,
            supersedes=[],
        )
        return
    if body.action == "replace":
        supersedes = _review_target_asset_ids(suggestion, body)
        await _register_suggestion_asset(
            registry,
            suggestion,
            current_user,
            supersedes=supersedes,
        )
        for asset_id in supersedes:
            await registry.set_status(asset_id, "archived")
        return
    if body.action == "retire":
        for asset_id in _review_target_asset_ids(suggestion, body):
            await registry.set_status(asset_id, "archived")
        return
    if body.action == "change_scope":
        if body.asset_id is None or body.scope is None:
            raise ValueError("Scope review actions require asset_id and scope")
        await registry.set_scope(body.asset_id, body.scope)
        return
    if body.action == "change_visibility":
        if body.asset_id is None or body.visibility is None:
            raise ValueError("Visibility review actions require asset_id and visibility")
        await registry.set_visibility(body.asset_id, body.visibility)


async def _register_suggestion_asset(
    registry: MemoryAssetRegistry,
    suggestion: MemorySuggestion,
    current_user: CurrentUser,
    *,
    supersedes: list[str],
) -> None:
    now = datetime.now(UTC).isoformat()
    await registry.register_asset(
        id=_suggestion_asset_id(suggestion),
        wiki_id=current_user.wiki_id,
        asset_type="wiki",
        layer="L1",
        name=_suggestion_asset_name(suggestion),
        scope=_suggestion_scope(suggestion, current_user.wiki_id),
        status="active",
        visibility=_suggestion_visibility(suggestion),
        summary=suggestion.rationale or _truncate(suggestion.proposed_markdown, 160),
        body=suggestion.proposed_markdown,
        tags=["suggestion", suggestion.suggestion_type],
        metadata={
            "suggestion_id": suggestion.id,
            "target_id": suggestion.target_id,
            "scores": suggestion.scores,
            "duplicates": suggestion.duplicates,
            "conflicts": suggestion.conflicts,
            "retention_tier": suggestion.retention_tier,
            "agent_visibility": suggestion.agent_visibility,
            "estimated_durability": suggestion.estimated_durability,
        },
        citations=_suggestion_citations(suggestion),
        approved_by=current_user.username,
        reviewed_at=now,
        supersedes=supersedes,
        conflict_lineage=[suggestion.id] if supersedes else [],
        change_note=f"Accepted review suggestion {suggestion.id}",
    )


def _suggestion_asset_id(suggestion: MemorySuggestion) -> str:
    return f"memory:suggestion:{suggestion.id}"


def _suggestion_asset_name(suggestion: MemorySuggestion) -> str:
    for line in suggestion.proposed_markdown.splitlines():
        cleaned = line.strip().lstrip("#").strip()
        if cleaned:
            return _truncate(cleaned, 80)
    return suggestion.suggestion_type


def _suggestion_scope(suggestion: MemorySuggestion, wiki_id: str) -> str:
    if suggestion.proposed_scopes:
        return suggestion.proposed_scopes[0]
    if suggestion.target_id.startswith("wiki:"):
        return f"wiki:{wiki_id}"
    return "person:self"


def _suggestion_visibility(suggestion: MemorySuggestion) -> str:
    if suggestion.agent_visibility in {"private", "shared", "public"}:
        return suggestion.agent_visibility
    return "private"


def _suggestion_citations(suggestion: MemorySuggestion) -> list[Citation]:
    citations: list[Citation] = []
    for raw in suggestion.citations:
        if isinstance(raw, Citation):
            citations.append(raw)
        elif isinstance(raw, dict):
            try:
                citations.append(Citation.model_validate(raw))
            except ValueError:
                continue
    return citations


def _review_target_asset_ids(
    suggestion: MemorySuggestion,
    body: ReviewSuggestionRequest,
) -> list[str]:
    candidates: list[str] = []
    if body.asset_id is not None:
        candidates.append(body.asset_id)
    if suggestion.target_id.startswith("memory:"):
        candidates.append(suggestion.target_id)
    candidates.extend(suggestion.conflicts)
    candidates.extend(suggestion.duplicates)
    seen: set[str] = set()
    asset_ids: list[str] = []
    for candidate in candidates:
        if candidate.startswith("memory:") and candidate not in seen:
            seen.add(candidate)
            asset_ids.append(candidate)
    return asset_ids


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else f"{value[: limit - 3]}..."


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
