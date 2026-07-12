# Archivum Project Progress

_Last updated: 2026-07-12_

## Status Vocabulary

- Verified: backed by a current test, command, or manual smoke result.
- Partial: implementation exists, but release behavior still needs proof or has known gaps.
- Started: early implementation exists.
- Unknown: code may exist, but current behavior has not been checked.
- Not built: no implementation found.

## Release Readiness

| Gate | Status | Evidence / owner |
|---|---|---|
| Open-source cleanup | Verified | PER-198 is In Review; private/generated project clutter was removed. |
| Apache 2.0 licensing | Verified | `LICENSE`, npm package metadata, and backend package metadata are Apache-2.0. |
| README product positioning | Verified | PER-218 ready for review. |
| Progress docs reconciled | Verified | PER-219 ready for review. |
| Docker Compose clean boot | Verified | PER-216 ready for review. Web UI, REST auth response, MCP SSE endpoint, and startup logs checked after local rebuild. |
| Ingest to wiki to query loop | Verified | PER-217 ready for review. Ingested `source.md`, created `source`, search found `AURORA-7112`, and query returned source citation plus the marker. |
| Backend pytest suite | Verified | Clean container copy ran `uv run --group dev pytest /tmp/workspace/tests -q`: 258 passed. |
| Frontend tests/build | Verified | `npm test --workspace apps/frontend`: 29 passed. `npm run build --workspace apps/frontend`: passed. |

## Product Surface

| Area | Status | Evidence |
|---|---|---|
| Markdown wiki pages | Verified | REST auth/list, ingest-created page persistence, search, and cited query were smoke-tested on 2026-07-12. |
| Vault navigation | Partial | Folder/page APIs and file tree UI exist. Frontend tests/build pass; browser click-through still needs manual smoke. |
| Wikilinks and backlinks | Partial | CodeMirror wikilink extension and backlinks API/UI exist. Needs browser smoke. |
| Ingest files and URLs | Verified | Markdown file ingest accepted and completed through Docker stack. URL ingest still needs separate release smoke. |
| Search | Partial | Qdrant semantic search returned the freshly ingested marker. Hybrid behavior needs product-level confirmation. |
| Query with citations | Verified | Query SSE returned citations including `source` and answered with `AURORA-7112`. |
| Graph | Partial | Kuzu graph API and frontend graph view exist. Needs browser smoke after Docker boot. |
| Sharing/export | Partial | Share links, public pages, HTML export, and PDF export code exist. Needs manual release smoke. |
| MCP server | Verified | Docker MCP SSE endpoint returned the session endpoint event; backend stdio smoke is covered by pytest. |
| Life OS workflows | Started | Daily/projects/tasks routes and UI exist; decisions/activity are first-pass screens, not release-gated. |

## Infrastructure

| Area | Status | Evidence |
|---|---|---|
| Docker Compose stack | Verified | `docker compose down && docker compose up -d --build` passed after adding frontend `depends_on` for backend startup order. |
| Data stores | Verified | Smoke covered SQLite page row, markdown output, Qdrant search, and Kuzu-backed startup. |
| Auth/security | Partial | Owner login, JWT cookies, CSRF, CSP, rate limiting, roles, and markdown sanitization exist. Needs release smoke. |
| Local install scripts | Unknown | README documents bootstrap/install/update/uninstall. Installer path still needs a fresh-machine pass before public release. |

## Verification Log

Add new entries with the exact command and result.

| Date | Check | Result |
|---|---|---|
| 2026-07-12 | Repo cleanup | Passed enough for PER-198 In Review. |
| 2026-07-12 | Apache 2.0 metadata | Passed; committed in `880fcf1`. |
| 2026-07-12 | Frontend tests | `npm test --workspace apps/frontend`: 29 passed. |
| 2026-07-12 | Frontend build | `npm run build --workspace apps/frontend`: passed with existing large chunk warning. |
| 2026-07-12 | Docker clean boot | `docker compose down && docker compose up -d --build`: passed after frontend/backend startup ordering fix. |
| 2026-07-12 | Runtime endpoints | `https://localhost` returned 200, protected REST returned expected 401 before login, authenticated `/api/pages` returned 200, and MCP `/sse` emitted endpoint event. |
| 2026-07-12 | Ingest/search/query | Uploaded `source.md`; ingest history completed with 1 page created; search and query found `AURORA-7112` with `source` citation. |
| 2026-07-12 | Backend pytest | Clean container copy ran `uv run --group dev pytest /tmp/workspace/tests -q`: 258 passed. |

## What To Build Next

1. PER-216 - Docker Compose clean boot.
2. PER-217 - ingest to wiki to query smoke.
3. PER-214 - backend pytest suite.
4. PER-215 - frontend tests and build.
5. PER-220 - page CRUD browser workflow.
6. PER-221 - autosave/load states.
7. PER-222 - wikilinks and backlinks UX.
8. PER-223 - vault drawer.
9. PER-224 - daily note workflow.
