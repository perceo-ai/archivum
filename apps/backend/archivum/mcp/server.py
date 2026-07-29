from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anthropic
from mcp.server.fastmcp import FastMCP

from archivum.capture.schema import Conversation, Turn
from archivum.capture.store import CaptureStore
from archivum.config import Settings, get_settings
from archivum.db import graph, qdrant_client as qdrant, sqlite
from archivum.ingest.pipeline import ingest
from archivum.ingest.agent import slugify
from archivum.life_os.service import ensure_daily_note, register_project
from archivum.linting import analyze_wiki_pages
from archivum.llm.openrouter_client import openrouter_chat_completion
from archivum.llm.openai_compat_client import openai_compat_chat_completion
from archivum.logging_config import setup_logging
from archivum.observability import new_trace_id, set_trace_id
from archivum import page_write_queue

logger = logging.getLogger(__name__)


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
    job_id = await sqlite.enqueue_page_write_job(
        slug=final_slug,
        title=title,
        content=content,
        tags=t,
        authored_by="agent",
        wiki_id=wiki_id,
    )
    job = await page_write_queue.wait_for_page_write_job(job_id, wiki_id=wiki_id)
    if job["status"] == "error":
        return {"error": "write_failed", "detail": job.get("error", "unknown write failure")}

    logger.info("MCP write_page done", extra={"slug": job.get("result_slug"), "wiki_id": wiki_id, "job_id": job_id})
    return await get_page(job["result_slug"], wiki_id)


@mcp.tool()
async def life_daily_note(day: str | None = None, wiki_id: str = "default") -> dict[str, Any]:
    """Create or return the daily note for YYYY-MM-DD."""
    _require_key()
    set_trace_id(new_trace_id("mcp-life-daily"))
    return await ensure_daily_note(day, wiki_id=wiki_id)


@mcp.tool()
async def life_register_project(
    key: str,
    name: str,
    summary: str = "",
    status: str = "active",
    wiki_id: str = "default",
) -> dict[str, Any]:
    """Register a project and create its canonical project page."""
    _require_key()
    set_trace_id(new_trace_id("mcp-life-project"))
    return await register_project(key, name, summary, status, wiki_id)


@mcp.tool()
async def life_create_task(
    title: str,
    project_key: str | None = None,
    page_slug: str | None = None,
    due_date: str | None = None,
    wiki_id: str = "default",
) -> dict[str, Any]:
    """Create a Life OS task linked to an optional project or page."""
    _require_key()
    set_trace_id(new_trace_id("mcp-life-task"))
    return await sqlite.create_life_task(
        wiki_id=wiki_id,
        title=title,
        project_key=project_key,
        page_slug=page_slug,
        due_date=due_date,
        source="mcp",
    )


@mcp.tool()
async def graph_neighbors(node_id: str, wiki_id: str = "default") -> dict[str, Any]:
    """Return Kuzu neighbors of a page/entity."""
    _require_key()
    set_trace_id(new_trace_id("mcp-graph"))
    data = await graph.get_neighbors(node_id, wiki_id)
    edges = [{"from": e["from"], "to": e["to"], "label": e.get("type", "")} for e in data.get("edges", [])]
    return {"center": data.get("center"), "nodes": data.get("nodes", []), "edges": edges}


@mcp.tool()
async def export_graph_demo(output_dir: str | None = None) -> dict[str, Any]:
    """Generate a self-contained demo graph export (no DB required)."""
    _require_key()
    set_trace_id(new_trace_id("mcp-graph-demo"))

    # Write to repo-owned fixtures by default.
    from archivum.scripts.graph_export import default_output_dir, export_demo

    out_path = default_output_dir() if not output_dir else Path(output_dir)
    result = export_demo(out_path)
    return {
        "ok": True,
        "tool": "export_graph_demo",
        "result": result,
    }


@mcp.tool()
async def lint_wiki(wiki_id: str = "default") -> dict[str, Any]:
    """Health check: broken wikilinks, orphan pages, and contradictory claims."""
    _require_key()
    set_trace_id(new_trace_id("mcp-lint"))
    pages = await sqlite.list_pages(wiki_id)
    analysis = analyze_wiki_pages(pages)
    broken = [
        {"type": i["type"], "page": i["page"], "target": i["target"]}
        for i in analysis["broken_wikilinks"]
    ]
    orphan = [i["page"] for i in analysis["orphan_pages"]]
    contradictory = [
        {
            "type": i["type"],
            "subject": i["subject"],
            "pages": i["pages"],
            "claims": i["claims"],
        }
        for i in analysis["contradictory_claims"]
    ]
    return {
        "broken_wikilinks": broken,
        "orphan_pages": orphan,
        "contradictory_claims": contradictory,
    }


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
    citation_rows = await sqlite.get_pages(slugs[:8], wiki_id)
    for row in citation_rows:
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


@mcp.tool()
async def dispatch_command(command: str, wiki_id: str = "default") -> dict[str, Any]:
    """Run a text command and dispatch to existing Archivum actions.

    Supported commands (case-insensitive):
    - help
    - ingest <source>
    - search <query>
    - query <question>
    - pages
    - open <slug>
    - write <json>|<title> | <content>
      - JSON form: write {"title":"...","content":"...","slug":"optional","tags":[...optional]}
      - Pipe form: write <title> | <content>
    - lint
    - graph <node_id>
    """
    _require_key()
    set_trace_id(new_trace_id("mcp-dispatch"))

    raw = (command or "").strip()
    if not raw:
        return {"error": "empty_command"}

    cmd, _, rest = raw.partition(" ")
    cmd = cmd.strip().lower()
    rest = rest.strip()

    def _err(code: str, detail: str) -> dict[str, Any]:
        return {"error": code, "detail": detail}

    try:
        if cmd in {"help", "?"}:
            return {
                "ok": True,
                "command": raw,
                "actions": [
                    "ingest <source>",
                    "search <query>",
                    "query <question>",
                    "pages",
                    "open <slug>",
                    "write <json> OR write <title> | <content>",
                    "lint",
                    "graph <node_id>",
                    "graph-export-demo [output_dir]",
                ],
            }

        if cmd in {"ingest", "ingest_source"}:
            if not rest:
                return _err("missing_argument", "Usage: ingest <source>")
            result = await ingest_source(rest, wiki_id=wiki_id)
            return {"ok": True, "command": raw, "tool": "ingest_source", "result": result}

        if cmd in {"search", "search_wiki"}:
            if not rest:
                return _err("missing_argument", "Usage: search <query>")
            result = await search_wiki(rest, wiki_id=wiki_id)
            return {"ok": True, "command": raw, "tool": "search_wiki", "result": result}

        if cmd in {"query", "ask"}:
            if not rest:
                return _err("missing_argument", "Usage: query <question>")
            result = await query(rest, wiki_id=wiki_id)
            return {"ok": True, "command": raw, "tool": "query", "result": result}

        if cmd in {"pages", "list_pages"}:
            result = await list_pages(wiki_id=wiki_id)
            return {"ok": True, "command": raw, "tool": "list_pages", "result": result}

        if cmd in {"open", "get", "get_page"}:
            if not rest:
                return _err("missing_argument", "Usage: open <slug>")
            result = await get_page(rest, wiki_id=wiki_id)
            return {"ok": True, "command": raw, "tool": "get_page", "result": result}

        if cmd in {"write", "edit", "write_page", "update"}:
            if not rest:
                return _err("missing_payload", "Usage: write <json> OR write <title> | <content>")

            payload: dict[str, Any]
            if rest.lstrip().startswith("{"):
                payload = json.loads(rest)
            else:
                # Pipe form: write <title> | <content>
                title, sep, content = rest.partition("|")
                if not sep:
                    return _err(
                        "invalid_payload",
                        "Expected JSON payload or pipe form: write <title> | <content>",
                    )
                payload = {"title": title.strip(), "content": content.strip()}

            title = payload.get("title")
            content = payload.get("content")
            slug = payload.get("slug")
            tags = payload.get("tags")

            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]

            if not isinstance(title, str) or not title.strip():
                return _err("invalid_payload", "Missing/invalid 'title' for write")
            if not isinstance(content, str):
                return _err("invalid_payload", "Missing/invalid 'content' for write")

            result = await write_page(
                title=title,
                content=content,
                slug=slug if isinstance(slug, str) and slug.strip() else None,
                tags=tags if isinstance(tags, list) else None,
                wiki_id=wiki_id,
            )
            return {"ok": True, "command": raw, "tool": "write_page", "result": result}

        if cmd in {"lint", "lint_wiki"}:
            result = await lint_wiki(wiki_id=wiki_id)
            return {"ok": True, "command": raw, "tool": "lint_wiki", "result": result}

        if cmd in {"graph-export-demo", "graph_export_demo", "export_graph_demo"}:
            result = await export_graph_demo(output_dir=rest or None)
            return {"ok": True, "command": raw, "tool": "export_graph_demo", "result": result}

        if cmd in {"graph", "graph_neighbors", "neighbors"}:
            if not rest:
                return _err("missing_argument", "Usage: graph <node_id>")
            result = await graph_neighbors(rest, wiki_id=wiki_id)
            return {"ok": True, "command": raw, "tool": "graph_neighbors", "result": result}

        return _err(
            "unknown_command",
            f"Unknown command '{cmd}'. Run 'help' for supported commands.",
        )

    except json.JSONDecodeError as e:
        return _err("invalid_json", f"Failed to parse JSON payload: {e}")
    except Exception as e:
        logger.exception("dispatch_command failed", extra={"command": raw, "wiki_id": wiki_id})
        return _err("command_failed", str(e))


async def capture_conversation_impl(
    *,
    session_id: str,
    interface: str = "claude_code_native",
    turns: list[dict[str, Any]],
    scope: str = "personal",
    origin_uri: str = "",
) -> dict[str, Any]:
    """Core (testable) capture path: build a Conversation and persist it."""
    conv = Conversation(
        session_id=session_id, interface=interface, started_at="",
        turns=tuple(
            Turn(role=t.get("role", "user"), text=t.get("text", ""),  # type: ignore[arg-type]
                 ts=t.get("ts", ""))
            for t in turns
        ),
        scope=scope, origin_uri=origin_uri,
    )
    store = CaptureStore(settings=get_settings())
    res = await store.capture(conv)
    return {
        "source_id": res.source_id,
        "content_hash": res.content_hash,
        "version": res.version,
        "chunks": len(res.chunk_ids),
        "deduplicated": res.deduplicated,
    }


@mcp.tool()
async def capture_conversation(
    session_id: str,
    interface: str = "claude_code_native",
    turns: list[dict[str, Any]] | None = None,
    scope: str = "personal",
) -> dict[str, Any]:
    """Capture a user-visible AI conversation as an immutable Source.

    `turns` is a list of {"role","text","ts?"} dicts. Hidden reasoning is stripped.
    """
    _require_key()
    set_trace_id(new_trace_id("mcp-capture"))
    return await capture_conversation_impl(
        session_id=session_id, interface=interface, turns=turns or [], scope=scope,
    )


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

    # Default to SSE for container usage. Host is set when FastMCP is created;
    # port is configured via MCP_PORT.
    logger.info("Starting MCP server (sse)", extra={"port": settings.mcp_port})
    mcp.run(transport="sse", mount_path="/")


if __name__ == "__main__":
    main()
