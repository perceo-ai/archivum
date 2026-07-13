# Archivum Project Progress

_Last updated: 2026-07-13_

## Status Vocabulary

- Verified: backed by a current test, command, or manual smoke result.
- Partial: implementation exists, but release behavior still needs proof or has known gaps.
- Started: early implementation exists.
- Unknown: code may exist, but current behavior has not been checked.
- Not built: no implementation found.

## Release Readiness

| Gate | Status | Evidence / owner |
|---|---|---|
| Open-source cleanup | Verified | Private/generated project clutter was removed before this docs pass. |
| Apache 2.0 licensing | Verified | `LICENSE`, npm package metadata, and backend package metadata are Apache-2.0. |
| README product positioning | Verified | README now describes Archivum as a self-hosted, server-hosted Obsidian-style second brain. |
| Docs pruning | Verified | Stale PRD, stale operator handoff, and duplicate root progress doc were removed on 2026-07-13. |
| Agent docs | Verified | `AGENTS.md`, `CLAUDE.md`, and `docs/agent-guide.md` point agents at current docs and verification commands. |
| Docker Compose clean boot | Verified | Previous smoke: clean Docker Compose boot, web UI, REST auth response, MCP SSE endpoint, and startup logs checked after local rebuild. Needs re-run before a public release cut. |
| Ingest to wiki to query loop | Verified | Previous smoke: markdown source ingested, search found marker text, and query returned source citation plus marker. Needs re-run before a public release cut. |
| Backend pytest suite | Verified | Previous clean container copy ran `uv run --group dev pytest /tmp/workspace/tests -q`: 258 passed. |
| Frontend tests/build | Verified | Previous checks: `npm test --workspace apps/frontend` passed 29 tests; `npm run build --workspace apps/frontend` passed. |

## Product Surface

| Area | Status | Evidence |
|---|---|---|
| Markdown wiki pages | Verified | REST auth/list, ingest-created page persistence, search, and cited query were smoke-tested on 2026-07-12. |
| Vault navigation | Partial | Folder/page APIs and file tree UI exist. Browser click-through still needs manual smoke. |
| Wikilinks and backlinks | Partial | CodeMirror wikilink extension and backlinks API/UI exist. Needs browser smoke. |
| Ingest files and URLs | Partial | Backend parser support is broad; markdown file ingest was smoked. URL and full format matrix still need release smoke. |
| Search | Partial | Qdrant semantic search returned freshly ingested marker text. Hybrid behavior needs product-level confirmation. |
| Query with citations | Verified | Query SSE returned citations including the source page and answered with the marker. |
| Graph | Partial | Kuzu graph API and frontend graph view exist. Needs browser smoke after Docker boot. |
| Sharing/export | Partial | Share links, public pages, HTML export, and PDF export code exist. Needs manual release smoke. |
| MCP server | Verified | Docker MCP SSE endpoint returned the session endpoint event; backend stdio smoke is covered by pytest. |
| Life OS workflows | Started | Daily/projects/tasks routes and UI exist. They are not the main public positioning. |

## Verification Log

Add new entries with the exact command and result.

| Date | Check | Result |
|---|---|---|
| 2026-07-12 | Frontend tests | `npm test --workspace apps/frontend`: 29 passed. |
| 2026-07-12 | Frontend build | `npm run build --workspace apps/frontend`: passed with existing large chunk warning. |
| 2026-07-12 | Docker clean boot | `docker compose down && docker compose up -d --build`: passed after frontend/backend startup ordering fix. |
| 2026-07-12 | Runtime endpoints | `https://localhost` returned 200, protected REST returned expected 401 before login, authenticated `/api/pages` returned 200, and MCP `/sse` emitted endpoint event. |
| 2026-07-12 | Ingest/search/query | Uploaded `source.md`; ingest history completed with 1 page created; search and query found the marker with source citation. |
| 2026-07-12 | Backend pytest | Clean container copy ran `uv run --group dev pytest /tmp/workspace/tests -q`: 258 passed. |
| 2026-07-13 | Docs update | README, docs index, architecture docs, progress, and agent docs were updated; stale PRD/operator/root progress docs were removed. |

## What To Build Next

1. Re-run clean Docker Compose boot and ingest/query smoke after docs review if cutting a release.
2. Smoke page CRUD, autosave, backlinks, and vault drawer in the browser.
3. Smoke URL ingest and a representative file-format matrix.
4. Smoke graph UI, share links, public wiki, HTML export, and PDF export.
