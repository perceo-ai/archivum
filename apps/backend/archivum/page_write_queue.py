from __future__ import annotations

import asyncio
import logging
from typing import Any

from archivum.config import Settings
from archivum.indexing import ensure_frontmatter, reindex_page
from archivum.db import graph, qdrant_client as qdrant, sqlite
from archivum.ingest.agent import slugify
from archivum.security.markdown import sanitize_markdown

logger = logging.getLogger(__name__)

_IDLE_POLL_SECONDS = 0.25
_WAIT_POLL_SECONDS = 0.1
_WAIT_TIMEOUT_SECONDS = 30.0


async def apply_page_write(
    *,
    title: str,
    content: str,
    slug: str | None,
    tags: list[str],
    authored_by: str,
    wiki_id: str,
    settings: Settings,
) -> dict[str, Any]:
    clean_content = sanitize_markdown(content or "")
    final_slug = slug or slugify(title)
    if not final_slug:
        raise ValueError("Could not generate slug from title")

    # Write the file, then reindex. This used to index first so that a failing
    # projection could not leave a visible row behind — the same worry that
    # `reindex_page` now handles properly, by treating the file and row as
    # canonical and letting projections degrade and be repaired later.
    stored = ensure_frontmatter(clean_content, title=title, tags=tags)
    wiki_path = settings.wiki_dir / f"{final_slug}.md"
    wiki_path.parent.mkdir(parents=True, exist_ok=True)
    wiki_path.write_text(stored, encoding="utf-8")

    await reindex_page(
        final_slug,
        wiki_id=wiki_id,
        settings=settings,
        force=True,
        authored_by=authored_by,
        reason="page-write-queue",
    )

    row = await sqlite.get_page(final_slug, wiki_id)
    if not row:
        raise RuntimeError(f"Page '{final_slug}' was not persisted")
    return dict(row)


async def wait_for_page_write_job(job_id: int, *, wiki_id: str, timeout_seconds: float = _WAIT_TIMEOUT_SECONDS) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while True:
        job = await sqlite.get_page_write_job(job_id, wiki_id)
        if not job:
            raise RuntimeError(f"Queued write job {job_id} disappeared")
        if job["status"] in {"done", "error"}:
            return job
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"Timed out waiting for write job {job_id}")
        await asyncio.sleep(_WAIT_POLL_SECONDS)


async def run_page_write_worker(settings: Settings) -> None:
    while True:
        job = await sqlite.claim_next_page_write_job()
        if not job:
            await asyncio.sleep(_IDLE_POLL_SECONDS)
            continue

        try:
            result = await apply_page_write(
                title=job["title"],
                content=job["content"],
                slug=job.get("slug"),
                tags=_coerce_tags(job.get("tags")),
                authored_by=job.get("authored_by") or "agent",
                wiki_id=job.get("wiki_id") or "default",
                settings=settings,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Page write job failed", extra={"job_id": job["id"], "wiki_id": job.get("wiki_id")})
            await sqlite.fail_page_write_job(job["id"], str(exc), wiki_id=job.get("wiki_id") or "default")
            continue

        await sqlite.complete_page_write_job(
            job["id"],
            result_slug=result["slug"],
            wiki_id=job.get("wiki_id") or "default",
        )


def _coerce_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(tag) for tag in raw]
    if isinstance(raw, str) and raw:
        import json

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(tag) for tag in parsed]
    return []
