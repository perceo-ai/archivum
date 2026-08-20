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
from archivum.ingest.events import publish
from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository
from archivum.linting import normalize_wikilink_target
from archivum.observability import new_trace_id, set_trace_id, span
from archivum.indexing import ensure_frontmatter, reindex_page
from archivum.pages_to_knowledge import sync_page_to_knowledge

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
    source_name: str | None = None,
) -> dict[str, Any]:
    """
    Full ingest pipeline for a single source (file path or URL).

    Returns a summary dict with pages_created, pages_updated, error.
    Streams progress events via progress_callback if provided.
    """
    s = settings or get_settings()
    source_str = str(source)
    display_source = source_name.strip() if source_name and source_name.strip() else source_str
    pages_created = 0
    pages_updated = 0
    log_id: int | None = None
    set_trace_id(new_trace_id("ingest"))

    async def emit(event: dict[str, Any]) -> None:
        await publish(wiki_id, event)
        if progress_callback:
            await progress_callback(event)

    # Determine source_type
    source_type = "url" if source_str.startswith("http") else "file"

    try:
        with span("sqlite.create_ingest_log", source=display_source, wiki_id=wiki_id) as sp_log:
            log_id = await sqlite.create_ingest_log(source_type, display_source, wiki_id)
        if log_id:
            set_trace_id(f"ingest-{log_id}")
        logger.info(
            "Ingest started",
            extra={"source_type": source_type, "source": display_source, "wiki_id": wiki_id, **sp_log},
        )
        await emit({"type": "start", "file": display_source, "log_id": log_id})

        # ── Step 1: Parse ──────────────────────────────────────────────────
        with span("parse_source", source=source_str) as sp_parse:
            doc = await parse_source(source)
        if source_name and source_type == "file":
            doc.source = display_source
            doc.metadata = {
                **doc.metadata,
                "filename": display_source,
                "title": doc.metadata.get("title") or Path(display_source).stem,
            }
        logger.info(
            "Parsed source",
            extra={"source": display_source, "chars": len(doc.text), "has_title": bool(doc.metadata.get("title")), **sp_parse},
        )
        await emit({"type": "parsed", "chars": len(doc.text), "source": display_source})

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

            # One indexing path, same as every other write. Ingest used to
            # fan out to SQLite, Qdrant, the graph and knowledge by hand, which
            # is how those stores drifted apart in the first place.
            existed = await sqlite.get_page(final_slug, wiki_id) is not None
            stored = ensure_frontmatter(
                page.content, title=page.title, tags=page.tags or []
            )
            wiki_path = s.wiki_dir / f"{final_slug}.md"
            wiki_path.parent.mkdir(parents=True, exist_ok=True)
            with span("disk.write_markdown", slug=final_slug) as sp_write:
                wiki_path.write_text(stored, encoding="utf-8")

            with span("indexing.reindex_page", slug=final_slug) as sp_index:
                index_result = await reindex_page(
                    final_slug,
                    wiki_id=wiki_id,
                    settings=s,
                    force=True,
                    authored_by="agent",
                    reason="ingest",
                )
                sp_index["degraded"] = ",".join(index_result.degraded)

            if existed:
                pages_updated += 1
            else:
                pages_created += 1
            created = not existed

            # Provenance is the part ingest adds on top: the page cites the
            # source it came from, which is what lets a source answer for its
            # own output later.
            async with sqlite.get_db() as conn:
                await _sync_extracted_result_to_knowledge(
                    KnowledgeRepository(conn),
                    result=ExtractionResult(pages=[page], entities=[], relationships=[]),
                    slug_map={page.slug: final_slug},
                    doc=doc,
                    wiki_id=wiki_id,
                    source_type=source_type,
                    display_source=display_source,
                )

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
                        **sp_index,
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

        async with sqlite.get_db() as conn:
            await _sync_extracted_result_to_knowledge(
                KnowledgeRepository(conn),
                result=ExtractionResult(
                    pages=[],
                    entities=result.entities,
                    relationships=result.relationships,
                ),
                slug_map=slug_map,
                doc=doc,
                wiki_id=wiki_id,
                source_type=source_type,
                display_source=display_source,
            )

        # ── Step 5: Wire wikilinks as REFERENCES edges ────────────────────
        with span("graph.wikilinks_and_mentions") as sp_links:
            ref_edges = 0
            mention_edges = 0
            for page in result.pages:
                final_slug = slug_map.get(page.slug, page.slug)
                wikilinks = _extract_wikilinks(page.content)
                for link_target in wikilinks:
                    target_slug = normalize_wikilink_target(link_target)
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
                "source": display_source,
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
    source_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Ingest multiple sources sequentially, streaming progress."""
    results = []
    for i, source in enumerate(sources):
        source_name = source_names[i] if source_names and i < len(source_names) else None
        display_source = source_name or str(source)

        async def _cb(event: dict, idx=i, display=display_source):
            if progress_callback:
                await progress_callback({**event, "file_index": idx, "file": display})

        result = await ingest(source, wiki_id, _cb, settings, source_name=source_name)
        results.append(result)
    return results


def _source_id(wiki_id: str, display_source: str) -> str:
    return f"source:{wiki_id}:{slugify(display_source) or 'source'}"


def _entity_id(wiki_id: str, name: str) -> str:
    return f"entity:{wiki_id}:{slugify(name) or 'entity'}"


def _source_citation(source_id: str, doc: ParsedDoc, quote: str | None = None) -> Citation:
    evidence = quote if quote is not None else doc.text[:500]
    start = doc.text.find(evidence) if evidence else -1
    return Citation(
        source_id=source_id,
        chunk_id=f"{source_id}:chunk:0",
        span_start=start if start >= 0 else None,
        span_end=start + len(evidence) if start >= 0 else None,
        quote=evidence or None,
    )


async def _sync_extracted_result_to_knowledge(
    repo: KnowledgeRepository,
    *,
    result: ExtractionResult,
    slug_map: dict[str, str],
    doc: ParsedDoc,
    wiki_id: str,
    source_type: str,
    display_source: str,
) -> None:
    """Persist ingest-produced records with source-backed extraction provenance."""
    scope = f"wiki:{wiki_id}"
    source_id = _source_id(wiki_id, display_source)
    source_label = str(doc.metadata.get("title") or display_source)
    source_citation = _source_citation(source_id, doc)
    await repo.upsert_object(
        KnowledgeObject(
            id=source_id,
            kind="source",
            label=source_label,
            scope=scope,
            confidence=1.0,
            extraction_method="EXTRACTED",
            citations=[source_citation],
            properties={
                "source_type": source_type,
                "origin_uri": display_source,
                "parser_source": doc.source,
                "metadata": doc.metadata,
            },
        )
    )
    await ensure_personal_root(repo, wiki_id=wiki_id)
    await link_to_self(repo, source_id, "saved_source", citation=source_citation)

    for page in result.pages:
        final_slug = slug_map.get(page.slug, page.slug)
        page_id = f"page:{wiki_id}:{final_slug}"
        page_citation = _source_citation(source_id, doc, page.title)
        await repo.upsert_object(
            KnowledgeObject(
                id=page_id,
                kind="page",
                label=page.title,
                scope=scope,
                confidence=0.8,
                extraction_method="EXTRACTED",
                citations=[page_citation],
                properties={
                    "slug": final_slug,
                    "wiki_id": wiki_id,
                    "markdown": page.content,
                    "source_type": source_type,
                    "origin_uri": display_source,
                },
            )
        )
        await repo.delete_relationships(
            src_id=SELF_ID,
            dst_id=page_id,
            rel_types={"authored_thought", "owns_project"},
        )
        await link_to_self(repo, page_id, "saved_source", citation=page_citation, confidence=0.8)

    for entity in result.entities:
        name = str(entity.get("name", "")).strip()
        if not name:
            continue
        entity_citation = _source_citation(source_id, doc, name)
        await repo.upsert_object(
            KnowledgeObject(
                id=_entity_id(wiki_id, name),
                kind="entity",
                label=name,
                scope=scope,
                confidence=0.7,
                extraction_method="EXTRACTED",
                citations=[entity_citation],
                properties={
                    "entity_type": str(entity.get("type") or "concept"),
                    "source_type": source_type,
                    "origin_uri": display_source,
                },
            )
        )

    for rel in result.relationships:
        from_name = str(rel.get("from", "")).strip()
        to_name = str(rel.get("to", "")).strip()
        if not from_name or not to_name:
            continue
        rel_type = slugify(str(rel.get("type") or "related_to")).replace("-", "_") or "related_to"
        src_id = _entity_id(wiki_id, from_name)
        dst_id = _entity_id(wiki_id, to_name)
        rel_citation = _source_citation(source_id, doc, f"{from_name} {to_name}")
        await repo.upsert_relationship(
            KnowledgeRelationship(
                id=f"rel:{src_id}:{rel_type}:{dst_id}",
                src_id=src_id,
                dst_id=dst_id,
                rel_type=rel_type,
                scope=scope,
                confidence=0.6,
                extraction_method="EXTRACTED",
                citations=[rel_citation],
                properties={"source_type": source_type, "origin_uri": display_source},
            )
        )
