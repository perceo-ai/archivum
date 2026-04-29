"""Ingest pipeline: orchestrates parser → agent → qdrant → kuzu → sqlite."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, AsyncGenerator, Callable, Awaitable

from archivum.config import Settings, get_settings
from archivum.db import sqlite, qdrant_client as qdrant, graph
from archivum.ingest.parsers import ParsedDoc, UnsupportedFileTypeError, parse_source
from archivum.ingest.agent import ExtractionResult, WikiPage, get_agent, slugify
from archivum.observability import new_trace_id, set_trace_id, span

logger = logging.getLogger(__name__)

# Type alias for the progress callback
ProgressCallback = Callable[[dict[str, Any]], Awaitable[None]]

_RESERVED_LOGRECORD_KEYS = frozenset(
    {
        # Core LogRecord attributes (covers common collisions).
        # https://docs.python.org/3/library/logging.html#logrecord-attributes
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "thread",
        "threadName",
    }
)


def _safe_extra(fields: dict[str, Any]) -> dict[str, Any]:
    """
    Avoid stdlib logging KeyError from `extra` collisions with LogRecord attributes.
    """
    out: dict[str, Any] = {}
    for k, v in fields.items():
        out[f"ctx_{k}" if k in _RESERVED_LOGRECORD_KEYS else k] = v
    return out


# ── Slug uniqueness ───────────────────────────────────────────────────────────

async def _unique_slug(base_slug: str, wiki_id: str) -> str:
    """Ensure the slug is unique in SQLite by appending -2, -3 etc."""
    slug = base_slug
    counter = 2
    while True:
        existing = await sqlite.get_page(slug, wiki_id)
        if existing is None:
            return slug
        slug = f"{base_slug}-{counter}"
        counter += 1


# ── Extract wikilinks ─────────────────────────────────────────────────────────

def _extract_wikilinks(content: str) -> list[str]:
    """Extract all [[wikilink]] targets from markdown content."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def ingest(
    source: str | Path,
    wiki_id: str = "default",
    progress_callback: ProgressCallback | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Full ingest pipeline for a single source (file path or URL).

    Returns a summary dict with pages_created, pages_updated, error.
    Streams progress events via progress_callback if provided.
    """
    s = settings or get_settings()
    source_str = str(source)
    pages_created = 0
    pages_updated = 0
    log_id: int | None = None
    set_trace_id(new_trace_id("ingest"))

    async def emit(event: dict[str, Any]) -> None:
        if progress_callback:
            await progress_callback(event)

    # Determine source_type
    source_type = "url" if source_str.startswith("http") else "file"

    try:
        with span("sqlite.create_ingest_log", source=source_str, wiki_id=wiki_id) as sp_log:
            log_id = await sqlite.create_ingest_log(source_type, source_str, wiki_id)
        if log_id:
            set_trace_id(f"ingest-{log_id}")
        logger.info(
            "Ingest started",
            extra={"source_type": source_type, "source": source_str, "wiki_id": wiki_id, **sp_log},
        )
        await emit({"type": "start", "file": source_str, "log_id": log_id})

        # ── Step 1: Parse ──────────────────────────────────────────────────
        with span("parse_source", source=source_str) as sp_parse:
            doc = await parse_source(source)
        logger.info(
            "Parsed source",
            extra={"source": source_str, "chars": len(doc.text), "has_title": bool(doc.metadata.get("title")), **sp_parse},
        )
        await emit({"type": "parsed", "chars": len(doc.text), "source": source_str})

        # ── Step 2: LLM extraction ─────────────────────────────────────────
        await emit({"type": "extracting", "message": "Running LLM extraction…"})
        agent = get_agent(s)
        with span("llm.extract", provider=s.llm_extraction_provider, model=s.llm_model) as sp_extract:
            result = await agent.extract(doc)
        logger.info(
            "LLM extraction finished",
            extra={
                "pages": len(result.pages),
                "entities": len(result.entities),
                "relationships": len(result.relationships),
                "provider": s.llm_extraction_provider,
                "model": s.llm_model,
                **sp_extract,
            },
        )
        await emit({"type": "extracted", "pages": len(result.pages), "entities": len(result.entities)})

        # ── Step 3: Persist each page ──────────────────────────────────────
        slug_map: dict[str, str] = {}  # original slug → final slug

        for idx, page in enumerate(result.pages):
            final_slug = await _unique_slug(page.slug, wiki_id)
            slug_map[page.slug] = final_slug

            # Write markdown to disk
            wiki_path = s.wiki_dir / f"{final_slug}.md"
            wiki_path.parent.mkdir(parents=True, exist_ok=True)
            with span("disk.write_markdown", slug=final_slug) as sp_write:
                wiki_path.write_text(page.content, encoding="utf-8")

            # Upsert into SQLite
            with span("sqlite.upsert_page", slug=final_slug) as sp_sql:
                _, created = await sqlite.upsert_page(
                    slug=final_slug,
                    title=page.title,
                    content=page.content,
                    tags=page.tags,
                    authored_by="agent",
                    wiki_id=wiki_id,
                )

            if created:
                pages_created += 1
            else:
                pages_updated += 1

            # Upsert into Qdrant
            with span("qdrant.upsert_page", slug=final_slug) as sp_q:
                chunk_count = await qdrant.upsert_page(
                    slug=final_slug,
                    title=page.title,
                    content=page.content,
                    wiki_id=wiki_id,
                    settings=s,
                )
                sp_q["chunks"] = chunk_count

            # Upsert page node in Kuzu
            with span("graph.upsert_page", slug=final_slug) as sp_g:
                await graph.upsert_page(final_slug, page.title, wiki_id)

            logger.info(
                "Persisted page",
                extra=_safe_extra(
                    {
                        "page_index": idx,
                        "slug": final_slug,
                        "page_created": created,
                        "title": page.title,
                        "tags": len(page.tags or []),
                        "content_chars": len(page.content or ""),
                        **sp_write,
                        **sp_sql,
                        **sp_q,
                        **sp_g,
                    }
                ),
            )

            event = {
                "type": "page_created" if created else "page_updated",
                "slug": final_slug,
                "title": page.title,
            }
            await emit(event)

        # ── Step 4: Graph — entities + relationships ───────────────────────
        entity_names: dict[str, str] = {}  # name → type

        with span(
            "graph.entities_and_relationships",
            entities=len(result.entities),
            relationships=len(result.relationships),
        ) as sp_graph:
            for entity in result.entities:
                name = entity.get("name", "").strip()
                etype = entity.get("type", "concept")
                if not name:
                    continue
                entity_names[name] = etype
                await graph.upsert_entity(name, etype, wiki_id)

            for rel in result.relationships:
                from_name = rel.get("from", "")
                to_name = rel.get("to", "")
                if from_name and to_name:
                    await graph.add_entity_relation(from_name, to_name, wiki_id)
        logger.info("Upserted entities + relationships", extra={**sp_graph})

        # ── Step 5: Wire wikilinks as REFERENCES edges ────────────────────
        with span("graph.wikilinks_and_mentions") as sp_links:
            ref_edges = 0
            mention_edges = 0
            for page in result.pages:
                final_slug = slug_map.get(page.slug, page.slug)
                wikilinks = _extract_wikilinks(page.content)
                for link_target in wikilinks:
                    target_slug = slugify(link_target)
                    target_page = await sqlite.get_page(target_slug, wiki_id)
                    if target_page:
                        await graph.add_reference(final_slug, target_slug, wiki_id)
                        ref_edges += 1

                for entity_name in entity_names:
                    if entity_name.lower() in page.content.lower():
                        await graph.add_mention(final_slug, entity_name, wiki_id)
                        mention_edges += 1
            sp_links["reference_edges"] = ref_edges
            sp_links["mention_edges"] = mention_edges
        logger.info("Wired wikilinks + mentions", extra={**sp_links})

        # ── Step 6: Finalise log ───────────────────────────────────────────
        with span("sqlite.update_ingest_log", log_id=log_id, status="done") as sp_done:
            await sqlite.update_ingest_log(
                log_id,
                status="done",
                pages_created=pages_created,
                pages_updated=pages_updated,
            )
        logger.info(
            "Ingest finished",
            extra={
                "source": source_str,
                "wiki_id": wiki_id,
                "pages_created": pages_created,
                "pages_updated": pages_updated,
                "entities_extracted": len(result.entities),
                "relationships_extracted": len(result.relationships),
                **sp_done,
            },
        )

        summary = {
            "type": "done",
            "pages_created": pages_created,
            "pages_updated": pages_updated,
            "entities_extracted": len(result.entities),
        }
        await emit(summary)
        return summary

    except UnsupportedFileTypeError as exc:
        logger.error("Unsupported file: %s", exc)
        error_msg = str(exc)
        if log_id:
            await sqlite.update_ingest_log(log_id, status="error", error=error_msg)
        await emit({"type": "error", "message": error_msg})
        return {"type": "error", "message": error_msg, "pages_created": 0, "pages_updated": 0}

    except Exception as exc:
        logger.exception("Ingest pipeline error for %s", source_str)
        error_msg = f"{type(exc).__name__}: {exc}"
        if log_id:
            await sqlite.update_ingest_log(log_id, status="error", error=error_msg)
        await emit({"type": "error", "message": error_msg})
        return {"type": "error", "message": error_msg, "pages_created": 0, "pages_updated": 0}


async def ingest_batch(
    sources: list[str | Path],
    wiki_id: str = "default",
    progress_callback: ProgressCallback | None = None,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Ingest multiple sources sequentially, streaming progress."""
    results = []
    for i, source in enumerate(sources):
        async def _cb(event: dict, src=source, idx=i):
            if progress_callback:
                await progress_callback({**event, "file_index": idx, "file": str(src)})

        result = await ingest(source, wiki_id, _cb, settings)
        results.append(result)
    return results
