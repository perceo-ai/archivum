from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from archivum.auth import CurrentUser, get_current_user
from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.llm.openrouter_client import openrouter_stream_tokens
from archivum.llm.openai_compat_client import openai_compat_stream_tokens
from archivum.retrieval.hybrid import hybrid_retrieve

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["query"])

_MAX_CONTEXTS = 6
_MAX_EXCERPT_CHARS = 1_200


class QueryRequest(BaseModel):
    question: str


def _build_prompt(question: str, contexts: list[dict[str, Any]]) -> str:
    ctx_lines: list[str] = []
    for i, c in enumerate(contexts[:_MAX_CONTEXTS], start=1):
        slug = c.get("slug", "")
        title = c.get("title", "")
        excerpt = (c.get("excerpt") or "").strip()[:_MAX_EXCERPT_CHARS]
        if not excerpt:
            continue
        ctx_lines.append(f"[{i}] {title} ({slug})\n{excerpt}\n")

    ctx_block = "\n\n".join(ctx_lines) if ctx_lines else "(No relevant context found.)"

    return (
        "You are Archivum, a knowledge base assistant. Answer using ONLY the provided context. "
        "Cite every factual claim with its bracketed context number. "
        "If the context is insufficient, explicitly say so.\n\n"
        f"Question:\n{question}\n\n"
        f"Context snippets:\n{ctx_block}\n\n"
        "Write a concise, helpful answer in markdown."
    )


@router.post("/query")
async def query(
    body: QueryRequest,
    current_user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> EventSourceResponse:
    question = body.question.strip()
    if not question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "Question cannot be empty", "code": "empty_question"},
        )

    if settings.llm_synthesis_provider == "anthropic" and not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "ANTHROPIC_API_KEY not configured", "code": "missing_api_key"},
        )
    if settings.llm_synthesis_provider == "openrouter" and not settings.openrouter_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "OPENROUTER_API_KEY not configured", "code": "missing_api_key"},
        )
    if settings.llm_synthesis_provider == "openai_compat" and not settings.openai_compat_api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": "OPENAI_COMPAT_API_KEY not configured", "code": "missing_api_key"},
        )

    logger.info(
        "API query start",
        extra={
            "wiki_id": current_user.wiki_id,
            "question_chars": len(question),
            "provider": settings.llm_synthesis_provider,
            "model": settings.llm_synthesis_model,
        },
    )

    hits = await hybrid_retrieve(
        question, current_user.wiki_id, limit=_MAX_CONTEXTS, settings=settings
    )
    contexts = [
        {
            "slug": _context_identifier(hit.id, current_user.wiki_id),
            "title": hit.label,
            "excerpt": hit.citation.quote or "",
            "score": hit.score,
        }
        for hit in hits
    ]
    slugs = [
        slug
        for hit in hits
        if (slug := _slug_from_page_id(hit.id, current_user.wiki_id)) is not None
    ]
    logger.info(
        "API query context ready",
        extra={
            "wiki_id": current_user.wiki_id,
            "hybrid_hits": len(hits),
            "contexts": len(contexts),
            "slugs": len(slugs),
        },
    )

    # Build citations (full page summaries) — batch to avoid N+1 sqlite calls.
    citations: list[dict[str, Any]] = []
    citation_rows = await sqlite.get_pages(slugs[:8], current_user.wiki_id)
    for row in citation_rows:
        citations.append(
            {
                "slug": row["slug"],
                "title": row["title"],
                "content": row["content"],
                "tags": json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "authored_by": row["authored_by"],
            }
        )

    prompt = _build_prompt(question, contexts)

    async def event_generator() -> AsyncGenerator[dict[str, str], None]:
        # Send citations first so UI can render sources panel early
        yield {"data": json.dumps({"type": "citations", "citations": citations})}

        try:
            if settings.llm_synthesis_provider == "anthropic":
                client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
                stream = await client.messages.create(
                    model=settings.llm_synthesis_model,
                    max_tokens=1024,
                    messages=[{"role": "user", "content": prompt}],
                    stream=True,
                )

                async for event in stream:
                    # anthropic SDK events vary; handle the common delta events
                    try:
                        if event.type == "content_block_delta" and getattr(event, "delta", None):
                            text = getattr(event.delta, "text", None)
                            if text:
                                yield {"data": json.dumps({"type": "token", "token": text})}
                    except Exception:
                        continue

            elif settings.llm_synthesis_provider == "openrouter":
                async for token in openrouter_stream_tokens(
                    settings=settings,
                    model=settings.llm_synthesis_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                    temperature=0.2,
                ):
                    yield {"data": json.dumps({"type": "token", "token": token})}
            elif settings.llm_synthesis_provider in {"openai_compat", "ollama"}:
                async for token in openai_compat_stream_tokens(
                    settings=settings,
                    provider=settings.llm_synthesis_provider,
                    model=settings.llm_synthesis_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1024,
                    temperature=0.2,
                ):
                    yield {"data": json.dumps({"type": "token", "token": token})}
            else:
                raise ValueError(f"Unsupported llm_synthesis_provider: {settings.llm_synthesis_provider}")

        except Exception as exc:
            logger.exception("Query synthesis error")
            yield {"data": json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"})}
        finally:
            logger.info("API query finished", extra={"wiki_id": current_user.wiki_id})
            yield {"data": "[DONE]"}

    return EventSourceResponse(event_generator())


def _slug_from_page_id(page_id: str, wiki_id: str) -> str | None:
    prefix = f"page:{wiki_id}:"
    return page_id.removeprefix(prefix) if page_id.startswith(prefix) else None


def _context_identifier(hit_id: str, wiki_id: str) -> str:
    return _slug_from_page_id(hit_id, wiki_id) or hit_id
