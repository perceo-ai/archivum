from __future__ import annotations

import argparse
import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import anthropic
from mcp.server.fastmcp import FastMCP

from archivum.config import Settings, get_settings
from archivum.db import graph, qdrant_client as qdrant, sqlite
from archivum.ingest.pipeline import ingest
from archivum.ingest.agent import slugify
from archivum.llm.openrouter_client import openrouter_chat_completion
from archivum.llm.openai_compat_client import openai_compat_chat_completion
from archivum.logging_config import setup_logging
from archivum.observability import new_trace_id, set_trace_id

logger = logging.getLogger(__name__)


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


@dataclass
class ToolContext:
    settings: Settings


settings = get_settings()
setup_logging()
set_trace_id(new_trace_id("mcp-startup"))
mcp = FastMCP(
    "Archivum",
    json_response=True,
    host="0.0.0.0",
    port=settings.mcp_port,
)


def _require_key() -> None:
    if settings.mcp_api_key:
        # FastMCP doesn't automatically enforce headers for stdio. We keep this as
        # a soft requirement in v1 (clients supply it via their own configuration).
        return


# ── Tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
async def ingest_source(source: str, wiki_id: str = "default") -> dict[str, Any]:
    """Process a file path or URL into the wiki."""
    _require_key()
    set_trace_id(new_trace_id("mcp-ingest"))
    logger.info("MCP ingest_source start", extra={"source": source, "wiki_id": wiki_id})

    events: list[dict[str, Any]] = []

    async def cb(ev: dict[str, Any]) -> None:
        events.append(ev)

    result = await ingest(source, wiki_id=wiki_id, progress_callback=cb, settings=settings)
    logger.info("MCP ingest_source done", extra={"source": source, "wiki_id": wiki_id, "result_type": result.get("type")})
    return {"result": result, "events": events[-50:]}  # keep response small


@mcp.tool()
async def search_wiki(query: str, top_k: int = 5, wiki_id: str = "default") -> list[dict[str, Any]]:
    """Semantic search; returns top-k with excerpts."""
    _require_key()
    set_trace_id(new_trace_id("mcp-search"))
    logger.info("MCP search_wiki", extra={"wiki_id": wiki_id, "top_k": top_k, "query_chars": len(query or "")})
    return await qdrant.search(query, wiki_id=wiki_id, limit=top_k, settings=settings)


@mcp.tool()
async def list_pages(wiki_id: str = "default") -> list[dict[str, Any]]:
    """List pages for a wiki."""
    _require_key()
    set_trace_id(new_trace_id("mcp-pages"))
    rows = await sqlite.list_pages(wiki_id)
    return [
        {
            "slug": r["slug"],
            "title": r["title"],
            "tags": json.loads(r["tags"]) if isinstance(r["tags"], str) else r["tags"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
            "authored_by": r["authored_by"],
        }
        for r in rows
    ]


@mcp.tool()
async def get_page(slug: str, wiki_id: str = "default") -> dict[str, Any]:
    """Retrieve full markdown content by slug."""
    _require_key()
    set_trace_id(new_trace_id("mcp-page"))
    row = await sqlite.get_page(slug, wiki_id)
    if not row:
        return {"error": "page_not_found", "slug": slug}
    return {
        "slug": row["slug"],
        "title": row["title"],
        "content": row["content"],
        "tags": json.loads(row["tags"]) if isinstance(row["tags"], str) else row["tags"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "authored_by": row["authored_by"],
    }


@mcp.tool()
async def write_page(
    title: str,
    content: str,
    slug: str | None = None,
    tags: list[str] | None = None,
    wiki_id: str = "default",
) -> dict[str, Any]:
    """Create or update a page and re-index."""
    _require_key()
    set_trace_id(new_trace_id("mcp-write"))
    final_slug = slug or slugify(title)
    if not final_slug:
        return {"error": "invalid_slug"}

    t = tags or []
    await sqlite.upsert_page(
        slug=final_slug,
        title=title,
        content=content,
        tags=t,
        authored_by="agent",
        wiki_id=wiki_id,
    )
    await qdrant.upsert_page(final_slug, title, content, wiki_id, settings)
    await graph.upsert_page(final_slug, title, wiki_id)

    logger.info(
        "MCP write_page indexed",
        extra={"slug": final_slug, "wiki_id": wiki_id, "title_chars": len(title or ""), "content_chars": len(content or "")},
    )
    return await get_page(final_slug, wiki_id)


@mcp.tool()
async def graph_neighbors(node_id: str, wiki_id: str = "default") -> dict[str, Any]:
    """Return Kuzu neighbors of a page/entity."""
    _require_key()
    set_trace_id(new_trace_id("mcp-graph"))
    data = await graph.get_neighbors(node_id, wiki_id)
    edges = [{"from": e["from"], "to": e["to"], "label": e.get("type", "")} for e in data.get("edges", [])]
    return {"center": data.get("center"), "nodes": data.get("nodes", []), "edges": edges}


@mcp.tool()
async def lint_wiki(wiki_id: str = "default") -> dict[str, Any]:
    """Health check: broken wikilinks + orphan pages (v1)."""
    _require_key()
    set_trace_id(new_trace_id("mcp-lint"))
    pages = await sqlite.list_pages(wiki_id)
    slug_set = {p["slug"] for p in pages}

    inbound: dict[str, int] = {s: 0 for s in slug_set}
    outbound: dict[str, int] = {s: 0 for s in slug_set}
    broken: list[dict[str, Any]] = []

    for p in pages:
        slug = p["slug"]
        content = p.get("content", "") or ""
        for target in (t.strip() for t in WIKILINK_RE.findall(content)):
            if not target:
                continue
            outbound[slug] = outbound.get(slug, 0) + 1
            if target in slug_set:
                inbound[target] = inbound.get(target, 0) + 1
            else:
                broken.append({"type": "broken_wikilink", "page": slug, "target": target})

    orphan = [s for s in slug_set if inbound.get(s, 0) == 0 and outbound.get(s, 0) == 0]
    return {"broken_wikilinks": broken, "orphan_pages": orphan}


@mcp.tool()
async def query(question: str, wiki_id: str = "default") -> dict[str, Any]:
    """Ask a question; returns synthesised answer with citations."""
    _require_key()
    set_trace_id(new_trace_id("mcp-query"))
    logger.info("MCP query start", extra={"wiki_id": wiki_id, "question_chars": len(question or "")})
    if settings.llm_synthesis_provider == "anthropic" and not settings.anthropic_api_key:
        return {"error": "missing_api_key", "detail": "ANTHROPIC_API_KEY not configured"}
    if settings.llm_synthesis_provider == "openrouter" and not settings.openrouter_api_key:
        return {"error": "missing_api_key", "detail": "OPENROUTER_API_KEY not configured"}
    if settings.llm_synthesis_provider == "openai_compat" and not settings.openai_compat_api_key:
        return {"error": "missing_api_key", "detail": "OPENAI_COMPAT_API_KEY not configured"}

    hits = await qdrant.search_raw(question, wiki_id=wiki_id, limit=6, settings=settings)
    by_slug: dict[str, dict[str, Any]] = {}
    for h in hits:
        s = h.get("slug")
        if not s:
            continue
        if s not in by_slug or float(h.get("score", 0)) > float(by_slug[s].get("score", 0)):
            by_slug[s] = h

    contexts = list(by_slug.values())
    slugs = [c.get("slug") for c in contexts if c.get("slug")]

    citations = []
    for slug in slugs[:8]:
        row = await sqlite.get_page(slug, wiki_id)
        if row:
            citations.append({"slug": row["slug"], "title": row["title"]})

    ctx_lines = []
    for i, c in enumerate(contexts, start=1):
        ctx_lines.append(f"[{i}] {c.get('title','')} ({c.get('slug','')})\n{(c.get('excerpt') or '')[:1200]}")

    prompt = (
        "Answer using ONLY the provided context snippets. If insufficient, say so.\n\n"
        f"Question:\n{question}\n\nContext:\n" + "\n\n".join(ctx_lines)
    )

    if settings.llm_synthesis_provider == "anthropic":
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        resp = await client.messages.create(
            model=settings.llm_synthesis_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        answer = (resp.content[0].text if resp.content else "").strip()
    elif settings.llm_synthesis_provider == "openrouter":
        answer = await openrouter_chat_completion(
            settings=settings,
            model=settings.llm_synthesis_model,
            max_tokens=1024,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
    elif settings.llm_synthesis_provider in {"openai_compat", "ollama"}:
        answer = await openai_compat_chat_completion(
            settings=settings,
            provider=settings.llm_synthesis_provider,
            model=settings.llm_synthesis_model,
            max_tokens=1024,
            temperature=0.2,
            messages=[{"role": "user", "content": prompt}],
        )
    else:
        return {
            "error": "unsupported_llm_synthesis_provider",
            "detail": f"Unsupported llm_synthesis_provider: {settings.llm_synthesis_provider}",
        }
    logger.info("MCP query done", extra={"wiki_id": wiki_id, "citations": len(citations), "answer_chars": len(answer or "")})
    return {"answer": answer, "citations": citations}


def main() -> None:
    parser = argparse.ArgumentParser(prog="archivum-mcp")
    parser.add_argument("--stdio", action="store_true", help="Run MCP over stdio")
    parser.add_argument("--sse", action="store_true", help="Run MCP over HTTP/SSE")
    args = parser.parse_args()

    if args.stdio and args.sse:
        raise SystemExit("Choose exactly one transport: --stdio or --sse")

    if args.stdio:
        logger.info("Starting MCP server (stdio)", extra={"port": settings.mcp_port})
        mcp.run(transport="stdio")
        return

    # Default to SSE for container usage
    # Host/port are configured via FASTMCP_HOST / FASTMCP_PORT env vars.
    logger.info("Starting MCP server (sse)", extra={"port": settings.mcp_port})
    mcp.run(transport="sse", mount_path="/")


if __name__ == "__main__":
    main()

