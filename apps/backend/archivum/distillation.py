"""Turn captured conversations into reviewable memory, in the background.

Distillation was fully built and never triggered. Nothing called it, so
`memory_assets` stayed empty, the review queue stayed empty, and the surfaces
built on top of them — what your agents know, what is waiting on you, the
memory pipeline — had nothing to show on a vault that had been running for
days. The pipeline existed; the pump did not.

It runs on a queue rather than inline because distillation may call an LLM.
Capture has to stay instant: you should be able to throw something at Archivum
and have it land whether or not a model is reachable, so capture enqueues and
returns, and this worker does the slow half.
"""

from __future__ import annotations

import asyncio
import logging

from archivum.capture.schema import Conversation, Turn
from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.memory.service import (
    DistillationError,
    DistillationReport,
    LoadedConversation,
    distill_conversation,
    load_conversation,
)

logger = logging.getLogger(__name__)

# A job that keeps failing is usually a malformed source, not a transient fault.
# Give up rather than spin, and leave the error on the row to be looked at.
MAX_ATTEMPTS = 3


async def distill_source(
    source_id: str, *, wiki_id: str, settings: Settings | None = None
) -> DistillationReport:
    """Distil one captured source into atoms, assets and review suggestions."""
    settings = settings or get_settings()
    loaded = await load_conversation(source_id, settings=settings)
    async with sqlite.get_db() as conn:
        return await distill_conversation(conn, loaded, wiki_id=wiki_id)


async def run_pending_distillations(*, settings: Settings | None = None, limit: int = 10) -> int:
    """Drain up to `limit` queued jobs. Returns how many were distilled."""
    settings = settings or get_settings()
    done = 0

    for _ in range(limit):
        job = await sqlite.claim_distillation()
        if job is None:
            break

        if job["attempts"] >= MAX_ATTEMPTS:
            await sqlite.finish_distillation(
                job["id"],
                status="error",
                error=f"gave up after {job['attempts']} attempts",
            )
            continue

        try:
            if job["kind"] == "page":
                report = await distill_page_job(job["source_id"], wiki_id=job["wiki_id"])
            else:
                report = await distill_source(
                    job["source_id"], wiki_id=job["wiki_id"], settings=settings
                )
        except DistillationError as exc:
            # The source is unusable — a permanent failure, not worth retrying.
            logger.warning("Distillation rejected %s: %s", job["source_id"], exc)
            await sqlite.finish_distillation(job["id"], status="error", error=str(exc))
            continue
        except Exception as exc:  # noqa: BLE001 - could be a flaky model call
            logger.warning("Distillation failed for %s: %s", job["source_id"], exc)
            await sqlite.finish_distillation(job["id"], status="pending", error=str(exc))
            continue

        logger.info(
            "Distilled %s: %d atom(s), %d pending review",
            job["source_id"],
            report.atoms_total,
            report.atoms_pending_review,
        )
        await sqlite.finish_distillation(job["id"], status="done")
        done += 1

    return done


async def run_distill_worker(settings: Settings) -> None:
    """Drain the distillation queue for the lifetime of the process."""
    interval = max(settings.distill_worker_interval_seconds, 1)
    logger.info("Distillation worker started", extra={"interval_s": interval})

    while True:
        try:
            await asyncio.sleep(interval)
            await run_pending_distillations(settings=settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - one bad pass must not stop the pump
            logger.warning("Distillation sweep failed: %s", exc)


def page_as_conversation(slug: str, title: str, markdown: str) -> LoadedConversation:
    """Present a page to the distiller as something it already understands.

    Only captured conversations were ever distilled, so a note you wrote by
    hand — the most deliberate thing in the vault — never proposed anything to
    remember. The atom extractor works on turns of text, and a page is text you
    authored, so it is expressed as a single authored turn rather than teaching
    the extractor a second input shape.

    Citations anchor to the page itself, which is the honest provenance: the
    claim came from this page, not from a chunk of some other source.
    """
    source_id = f"page:{slug}"
    conversation = Conversation(
        session_id=f"page:{slug}",
        interface="vault",
        started_at="",
        turns=(Turn(role="user", text=markdown),),
        origin_uri=slug,
        metadata={"title": title, "slug": slug, "kind": "page"},
    )
    chunk_id = f"{source_id}:chunk:0"
    return LoadedConversation(
        conversation=conversation,
        source_id=source_id,
        chunk_ids=[chunk_id],
        chunk_offsets={chunk_id: 0},
    )


async def distill_page(
    slug: str, *, title: str, markdown: str, wiki_id: str
) -> DistillationReport:
    """Propose memory from a page you wrote, for you to review."""
    loaded = page_as_conversation(slug, title, markdown)
    async with sqlite.get_db() as conn:
        return await distill_conversation(conn, loaded, wiki_id=wiki_id)


async def distill_page_job(slug: str, *, wiki_id: str) -> DistillationReport:
    """Distil a queued page, reading its current content from the store."""
    row = await sqlite.get_page(slug, wiki_id)
    if row is None:
        raise DistillationError(f"Page '{slug}' no longer exists")
    return await distill_page(
        slug, title=row["title"], markdown=row["content"], wiki_id=wiki_id
    )
