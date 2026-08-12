# Archivum Project Progress

_Last updated: 2026-08-12_

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
| Docker Compose clean boot | Partial | 2026-08-12 Task 12 rebuilt-stack smoke blocked: `docker compose up -d --build` built/exported backend and MCP images, then hung while loading frontend base image metadata for `docker.io/library/node:20-alpine` / `docker.io/library/nginx:alpine`; command was stopped with exit 130 after repeated no-progress waits. Pre-existing stack endpoint probe still returned frontend 200, protected `/api/pages` 401, authenticated `/api/pages` 200, and MCP SSE endpoint event. |
| Ingest to wiki to query loop | Verified | 2026-08-12 local current-code smoke: markdown file ingest returned 200/accepted, search found `ARCHIVUM_TASK12_INGEST_MARKER_20260811212638`, `/api/retrieve` returned cited evidence, and `/api/query` SSE emitted citations and an answer containing the page marker. |
| Backend pytest suite | Verified | 2026-08-12: `cd apps/backend && uv run --group dev pytest ../../tests -q`: first run failed during collection because duplicate test basenames in `tests/knowledge` and `tests/store` were un-packaged; after adding package markers, 469 passed. |
| Frontend tests/build | Verified | 2026-08-12: `npm test --workspace apps/frontend`: 54 passed; `npm run build --workspace apps/frontend`: passed with existing large chunk warning. |
| CLI tests | Verified | 2026-08-12: `npm test --workspace packages/archivum-cli`: 18 passed. |

## Product Surface

| Area | Status | Evidence |
|---|---|---|
| Markdown wiki pages | Verified | REST auth/list, ingest-created page persistence, search, and cited query were smoke-tested on 2026-07-12. |
| Vault navigation | Partial | Folder/page APIs and file tree UI exist. Browser click-through still needs manual smoke. |
| Wikilinks and backlinks | Partial | CodeMirror wikilink extension exists; 2026-08-12 current-code smoke preserved edited wikilinks and canonical context contained the `references` edge, but legacy `/api/pages/{slug}/backlinks` returned `[]` for a display-text wikilink because the legacy graph sync checks raw wikilink text against page slugs. Browser editor click-through still needs manual smoke. |
| Ingest files and URLs | Partial | Backend parser support is broad; markdown file ingest was smoked. URL and full format matrix still need release smoke. |
| Search | Partial | Qdrant semantic search returned freshly ingested marker text. Hybrid behavior needs product-level confirmation; canonical retrieval defaults to `person:self` when no seed is supplied. |
| Query with citations | Verified | Query SSE returned citations including the source page and answered with the marker; canonical context carries citations, confidence, and extraction method. |
| Graph | Partial | 2026-08-12 local current-code context smoke opened a bounded package seeded at `person:self` with 4 nodes and `authored_thought`/`owns_project` edges. Legacy graph API and browser graph view still need rebuilt Docker/browser smoke. |
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
| 2026-08-12 | Backend pytest | `cd apps/backend && uv run --group dev pytest ../../tests -q`: first run failed during collection with import mismatch for duplicate `test_models.py` and `test_repository.py`; after adding `tests/knowledge/__init__.py` and `tests/store/__init__.py`, rerun passed with 469 passed in 7.89s. |
| 2026-08-12 | Frontend tests | `npm test --workspace apps/frontend`: 11 test files passed, 54 tests passed. |
| 2026-08-12 | Frontend build | `npm run build --workspace apps/frontend`: passed; Vite reported the existing warning that some chunks exceed 500 kB after minification. |
| 2026-08-12 | CLI tests | `npm test --workspace packages/archivum-cli`: 18 passed, 0 failed. |
| 2026-08-12 | Docker build/start | `docker compose up -d --build`: blocked for rebuilt-stack smoke. Backend and MCP images built/exported, but the command twice stalled while loading frontend base image metadata for `docker.io/library/node:20-alpine` / `docker.io/library/nginx:alpine`; both attempts were stopped with exit 130 after repeated no-progress waits. |
| 2026-08-12 | Pre-existing Docker endpoints | Existing running stack probe: `https://localhost/` returned 200; unauthenticated `https://localhost/api/pages` returned 401; login returned 200; authenticated `https://localhost/api/pages` returned 200; `http://localhost:8001/sse` with MCP bearer key emitted `event: endpoint` before curl timed out at 5 seconds. |
| 2026-08-12 | Local current-code product smoke | Local backend from current workspace on `127.0.0.1:18080` with isolated `/tmp/archivum-task12-local` data: login 200; target page create 201; owner project page create 201; page edit 200; page fetch 200 and markdown edit marker/wikilinks preserved; markdown file ingest 200 accepted; search 200 found `ARCHIVUM_TASK12_INGEST_MARKER_20260811212638`; `/api/context-package` 200 returned 4 bounded nodes including `person:self`, the owner project, linked target, and ingested page with `references`, `owns_project`, and `authored_thought` edges; `seed_ids:["person:self"]` context returned `person:self` plus owner-centered edges; `/api/retrieve` 200 returned 5 hits with citations and `insufficient_evidence:false`; `/api/query` SSE emitted citations and an answer containing `ARCHIVUM_TASK12_PAGE_MARKER_20260811212638`. Legacy `/api/pages/{target}/backlinks` returned 200 with `[]` for the display-text wikilink, so legacy backlink smoke failed even though canonical context contained the reference edge. |
| 2026-08-12 | Suggestion lifecycle | Explicit suggestion acceptance/rejection is covered by `tests/knowledge/test_suggestions.py` within the 469-test backend suite, including accept-once, reject, conflicting transitions, JSON payload round trip, and acceptance not mutating markdown/canonical objects. No product REST endpoint exists to manually accept/reject a suggestion through HTTP in this smoke. |

## What To Build Next

1. Smoke page CRUD, autosave, backlinks, and vault drawer in the browser.
2. Smoke the Settings LLM provider form in the browser.
3. Smoke URL ingest and a representative file-format matrix.
4. Smoke graph UI, share links, public wiki, HTML export, and PDF export.
