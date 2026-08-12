# Archivum Project Progress

_Last updated: 2026-08-11_

Archivum keeps markdown editable for humans while maintaining rebuildable semantic and graph indexes for search, citations, and agent context. Canonical knowledge is owner-centered at `person:self`; retrieval and MCP context preserve citations, confidence, and extraction method.

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
| Docker Compose clean boot | Verified | 2026-08-11 smoke: `docker compose up -d --build` completed; containers started; `https://localhost` returned 200; protected `/api/pages` returned 401 before login; authenticated `/api/pages` returned 200; MCP `/sse` emitted an endpoint event. |
| Ingest to wiki to query loop | Verified | 2026-08-11 smoke: markdown upload created 1 page; search found `ARCHIVUM_SMOKE_MARKER_20260811`; `/api/query` emitted citations and streamed tokens from hosted Ollama-compatible synthesis. |
| Backend pytest suite | Verified | 2026-08-11: `cd apps/backend && uv run --group dev pytest ../../tests -q`: 358 passed. |
| Frontend tests/build | Verified | 2026-08-11: `npm test --workspace apps/frontend`: 33 passed; `npm run build --workspace apps/frontend`: passed with existing large chunk warning. |

## Product Surface

| Area | Status | Evidence |
|---|---|---|
| Markdown wiki pages | Verified | REST auth/list, ingest-created page persistence, search, and cited query were smoke-tested on 2026-07-12. |
| Vault navigation | Partial | Folder/page APIs and file tree UI exist. Browser click-through still needs manual smoke. |
| Wikilinks and backlinks | Partial | CodeMirror wikilink extension exists; 2026-08-11 API smoke verified page-created wikilinks produce backlink results. Browser editor click-through still needs manual smoke. |
| Ingest files and URLs | Partial | Backend parser support is broad; markdown file ingest was smoked. URL and full format matrix still need release smoke. |
| Search | Partial | Qdrant semantic search returned freshly ingested marker text. Hybrid behavior needs product-level confirmation; canonical retrieval defaults to `person:self` when no seed is supplied. |
| Query with citations | Verified | Query SSE returned citations including the source page and answered with the marker; canonical context carries citations, confidence, and extraction method. |
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
| 2026-08-11 | Frontend tests | `npm test --workspace apps/frontend`: 33 passed. |
| 2026-08-11 | Frontend build | `npm run build --workspace apps/frontend`: passed with existing large chunk warning. |
| 2026-08-11 | CLI tests | `npm test --workspace packages/archivum-cli`: 17 passed. |
| 2026-08-11 | Backend pytest | `cd apps/backend && uv run --group dev pytest ../../tests -q`: 358 passed. |
| 2026-08-11 | Docker boot and endpoints | `docker compose up -d --build`: passed; `https://localhost` returned 200; unauthenticated `/api/pages` returned 401; authenticated `/api/pages` returned 200; MCP `http://localhost:8001/sse` emitted endpoint event. |
| 2026-08-11 | Ingest/search/query | Uploaded `archivum-smoke-source.md`; ingest history completed with 1 page created; search found `ARCHIVUM_SMOKE_MARKER_20260811`; `/api/query` emitted citations and streamed tokens through hosted Ollama-compatible config. |
| 2026-08-11 | Page backlinks | Created fresh source/target pages; `/api/pages/{target}/backlinks` returned the source page. |
| 2026-08-11 | Recovery backup/validate | `archivum recovery backup --dir=.context/recovery-smoke-20260811-1615` created config and precious-volume archives; `archivum recovery validate .context/recovery-smoke-20260811-1615` passed; stack returned healthy with web 200, protected API 401, and MCP SSE endpoint event. |

## What To Build Next

1. Smoke page CRUD, autosave, backlinks, and vault drawer in the browser.
2. Smoke the Settings LLM provider form in the browser.
3. Smoke URL ingest and a representative file-format matrix.
4. Smoke graph UI, share links, public wiki, HTML export, and PDF export.
