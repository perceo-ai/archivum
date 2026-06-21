# Archivum Second-Brain MVP Progress

_Last updated: 2026-06-21_

## MVP Target

Build Archivum into a daily-use second brain for one owner:

- A functioning MCP server that lets agents read, search, query, write, ingest, lint, and inspect the knowledge base.
- An Obsidian-like web interface for editing markdown, navigating backlinks, searching, viewing the graph, ingesting sources, and asking questions.
- A Life OS layer that captures daily notes, tasks, decisions, projects, people, areas, and agent activity in structured pages agents can use safely.
- Local-first deployment through Docker Compose with durable SQLite, Qdrant, Kuzu, raw source storage, and markdown content.

## Current Codebase Status

| Area | Status | Evidence |
|---|---|---|
| Backend API | Built, Life OS backend started | FastAPI app under `apps/backend/archivum`; routes for pages, folders, ingest, query, graph, search, lint, share, export, auth, public pages, system maintenance, plus `/api/life/daily`, `/api/life/projects`, and `/api/life/tasks` |
| MCP server | Built, Life OS tools started | `apps/backend/archivum/mcp/server.py` exposes existing wiki tools plus `life_daily_note`, `life_register_project`, and `life_create_task`; `make mcp-smoke` passed on 2026-06-21 |
| Obsidian-like editor | Built foundation | React/Vite UI has wiki editor, file tree, backlinks, graph, query, ingest, search, lint, settings |
| Storage | Built foundation, Life OS schema started | SQLite metadata and FTS, Qdrant vectors, Kuzu graph, raw source directory; Life OS tables now include projects, tasks, decisions, people, areas, and agent activity |
| Ingest | Built foundation | Parsers and pipeline exist for documents, web, code, email, media extras, and batch ingest |
| Search and retrieval | Mostly built | Qdrant semantic search and SQLite FTS exist; hybrid ranking needs product-level confirmation |
| Security | Mostly built | Auth, JWT cookies, roles, CSRF, CSP, rate limiting, markdown sanitization, share controls |
| Sharing/export | Built foundation | Share links, public wiki, PDF/HTML export endpoints and UI hooks exist |
| Life OS concepts | Backend/MCP foundation started | Daily note, project registry, and task capture are available through SQLite helpers, REST endpoints, and MCP tools; dedicated frontend views and decision/activity workflows are still pending |
| Agent activity ledger | Not yet built as first-class workflow | MCP writes pages, but there is no normalized run/activity log, inbox, or provenance dashboard |
| Personal import/export | Partial | General ingest/export exists; Life OS import conventions and Obsidian-compatible vault export are not defined |

## MVP Definition Of Done

- `docker compose up` boots the app, backend, MCP server, Qdrant, and Caddy from a clean checkout after `.env` setup.
- MCP Inspector or equivalent smoke tests confirm both stdio and SSE transports expose the expected tools.
- The web UI supports the daily second-brain loop: capture, edit, link, query, inspect graph, review backlinks, manage ingest, and resolve lint issues.
- Life OS entities are represented consistently: daily notes, projects, areas, tasks, decisions, people, sources, and agent runs.
- Agents can use MCP tools for Life OS workflows without scraping UI state.
- Search returns useful answers across semantic hits, exact keyword hits, tags, and Life OS metadata.
- The system can import an existing notes folder and export an Obsidian-readable markdown vault.
- Tests cover backend APIs, MCP tools, core DB behavior, and frontend flows touched by the MVP.
- README includes personal setup, MCP client config, Life OS conventions, backup/restore, and recovery instructions.

## Prioritized Work

1. Add Obsidian-like UI affordances for second-brain workflows: command palette, daily note button, project dashboard, task/decision views, and backlinks/graph improvements.
2. Add decision/activity workflow endpoints and MCP tools.
3. Add Life OS page conventions and docs.
4. Add import/export conventions for Obsidian vaults and Life OS bundles.
5. Add activity/provenance logging for agent changes and ingest runs.
6. Harden verification: MCP stdio/SSE smoke tests, Playwright UI flows, backend integration tests, and Docker boot checks.
7. Update README and operator docs for personal deployment and project integration.

## Active Implementation Plan

Full task-by-task plan: `docs/superpowers/plans/2026-06-21-second-brain-mvp.md`

## Open Decisions

- Whether Life OS structured entities should remain derived from markdown frontmatter only, or also live in normalized SQLite tables. Current plan uses both: markdown stays portable; SQLite gives reliable API/MCP queries.
- Whether tasks should be simple markdown checkboxes for MVP or full recurring/scheduled task objects. Current plan starts with simple task rows plus page links.
- Whether project integration should sync from external project folders automatically. Current plan starts with explicit import/register actions to avoid unsafe filesystem crawling.
- Whether to expose write-capable MCP over SSE outside localhost. Current plan keeps write-capable MCP local/private by default and documents reverse-proxy risks.
