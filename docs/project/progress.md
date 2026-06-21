# Archivum — Build Progress

_Last updated: 2026-06-21_

---

## Overall Status

**v1 FEATURE-COMPLETE; second-brain MVP backend phase in progress** — Life OS storage, daily/project/task REST endpoints, and matching MCP tools are now started. Remaining second-brain MVP work includes frontend Life OS views, decision/activity workflows, import/export conventions, and final end-to-end validation.

---

## Second-Brain MVP Update

| Feature | Status | Notes |
|---|---|---|
| Life OS SQLite schema | ✅ Started | `life_projects`, `life_tasks`, `life_decisions`, `life_people`, `life_areas`, and `agent_activity` tables added in `apps/backend/archivum/db/sqlite.py` |
| Daily note service | ✅ Started | `ensure_daily_note()` creates portable markdown pages with `type: daily` frontmatter |
| Project registry service | ✅ Started | `register_project()` creates canonical `project-*` pages and project rows |
| Task capture | ✅ Started | REST and MCP can create/list task rows; first-pass task UI is available at `/tasks` |
| Life OS REST API | ✅ Started | `/api/life/daily`, `/api/life/projects`, and `/api/life/tasks` mounted |
| Life OS MCP tools | ✅ Started | `life_daily_note`, `life_register_project`, and `life_create_task` added; stdio smoke still passes |
| Life OS frontend | ✅ Started | `/daily`, `/projects`, `/tasks`, `/decisions`, and `/activity` routes are mounted with first-pass UI |

---

## Epic 1: Ingest

| Feature | Status | Notes |
|---|---|---|
| Ingest pipeline (parse → LLM → SQLite + Qdrant + Kuzu) | ✅ Done | `backend/archivum/ingest/pipeline.py` |
| SSE progress streaming per file | ✅ Done | `api/ingest.py` |
| Batch ingest (up to 20 files, sequential) | ✅ Done | `ingest_batch()` in pipeline |
| Ingest history log | ✅ Done | SQLite `ingest_log` table |
| Drag & drop ingest UI | ✅ Done | `frontend/src/components/IngestPanel.tsx` |
| URL ingest | ✅ Done | httpx + readability + BeautifulSoup |
| Parser: `.md`, `.txt`, `.rst` | ✅ Done | Native, frontmatter included |
| Parser: `.pdf` | ✅ Done | PyMuPDF |
| Parser: `.html`, `.htm` | ✅ Done | BeautifulSoup + readability |
| Parser: `.docx` | ✅ Done | python-docx |
| Parser: `.pptx` | ✅ Done | python-pptx |
| Parser: `.xlsx`, `.xls`, `.csv` | ✅ Done | pandas + openpyxl fallback |
| Parser: `.json`, `.jsonl` | ✅ Done | stdlib json |
| Parser: `.epub` | ✅ Done | ebooklib |
| Parser: code files (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.sh`, etc.) | ✅ Done | 20+ languages |
| Parser: `.srt`, `.vtt` (subtitles/transcripts) | ✅ Done | Native, strips timestamps |
| Parser: `.eml` | ✅ Done | stdlib email |
| Parser: images (`.png`, `.jpg`, `.webp`, `.gif`) — Claude vision | ✅ Done | `ingest/parsers.py` |
| Parser: audio (`.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac`) — optional Whisper | ✅ Done | `ingest/parsers.py`; packaged behind the `audio` extra |
| Parser: video (`.mp4`, `.mov`, `.avi`, `.mkv`) — optional ffmpeg → Whisper | ✅ Done | `ingest/parsers.py`; packaged behind the `audio` extra |
| Parser: `.mbox` | ✅ Done | stdlib mailbox parser in `ingest/parsers.py` |

---

## Epic 2: Editor

| Feature | Status | Notes |
|---|---|---|
| CodeMirror 6 with markdown syntax highlighting | ✅ Done | `Editor.tsx` + `wikilinkExtension.ts` |
| `[[wikilink]]` autocomplete + broken-link detection | ✅ Done | Custom CM6 extension |
| Auto-save (debounced 1s) | ✅ Done | via `PUT /api/pages/:slug` |
| Backlinks panel | ✅ Done | `BacklinksPanel.tsx` + `GET /api/pages/:slug/backlinks` |
| File tree sidebar (create / delete) | ✅ Done | `FileTree.tsx` |
| Page CRUD (create, read, update, delete) | ✅ Done | `api/pages.py` — full REST |

---

## Epic 3: Graph View

| Feature | Status | Notes |
|---|---|---|
| Force-directed graph (vis-network) | ✅ Done | `GraphView.tsx` |
| Nodes colour-coded by type | ✅ Done | Page, entity, concept nodes |
| Edges with relationship labels | ✅ Done | REFERENCES, MENTIONS, RELATED |
| Click node → open wiki page | ✅ Done | `loadGraph()` / `renderGraph()` |
| Zoom, pan, search / highlight | ✅ Done | vis-network built-ins |
| Graph API (neighbors, all nodes/edges, rebuild) | ✅ Done | `api/graph.py` |

---

## Epic 4: Query

| Feature | Status | Notes |
|---|---|---|
| Streaming SSE query (token-by-token) | ✅ Done | `api/query.py` + `QueryPanel.tsx` |
| Citations panel linked to source pages | ✅ Done | sent before tokens via SSE |
| Save query answer as wiki page | ✅ Done | "Save as page" button in QueryPanel |
| Query via MCP | ✅ Done | `query` tool in `mcp/server.py` |

---

## Epic 5: Search

| Feature | Status | Notes |
|---|---|---|
| Semantic search via Qdrant | ✅ Done | `api/search.py` + `db/qdrant_client.py` |
| Search bar in UI | ✅ Done | `SearchBar.tsx` |
| Keyword fallback | ❓ Unknown | Qdrant supports hybrid — not confirmed wired |

---

## Epic 6: MCP Server

| Feature | Status | Notes |
|---|---|---|
| SSE transport (`localhost:8001`) | ✅ Done | FastMCP with `--sse` |
| stdio transport | ✅ Done | FastMCP with `--stdio` |
| `ingest_source` tool | ✅ Done | Runs full pipeline |
| `search_wiki` tool | ✅ Done | Qdrant semantic search |
| `get_page` tool | ✅ Done | Returns full markdown |
| `list_pages` tool | ✅ Done | Lists all pages |
| `write_page` tool | ✅ Done | Create or update + re-index |
| `query` tool | ✅ Done | LLM synthesis with citations |
| `graph_neighbors` tool | ✅ Done | Kuzu neighbors |
| `lint_wiki` tool | ✅ Done | Broken wikilinks + orphans |
| MCP Inspector validation | ✅ Done | `tools/list` passed for stdio and SSE via `@modelcontextprotocol/inspector` |
| Client config snippets in README | ✅ Done | README.md |

---

## Epic 7: Lint

| Feature | Status | Notes |
|---|---|---|
| Broken wikilink detection | ✅ Done | `GET /api/lint` + MCP `lint_wiki` |
| Orphan page detection | ✅ Done | Same endpoints |
| One-click fix UI | ✅ Done | LintPage.tsx + `POST /api/lint/fix` |
| Contradiction detection | ✅ Done | Deterministic enabled/disabled claim checks in `/api/lint` and MCP `lint_wiki` |

---

## Infrastructure

| Feature | Status | Notes |
|---|---|---|
| Docker Compose stack (all services) | ✅ Done | `docker-compose.yml` |
| Backend (FastAPI Python 3.12) | ✅ Done | Port 8000 behind Caddy |
| Frontend (React + Vite + TypeScript) | ✅ Done | nginx, port 3000 behind Caddy |
| MCP server (stdio + SSE) | ✅ Done | Port 8001 |
| Qdrant vector DB | ✅ Done | Internal only, healthcheck |
| Kuzu embedded graph DB (chose over Neo4j) | ✅ Done | Saves ~2 GB RAM vs Neo4j |
| SQLite WAL for metadata | ✅ Done | Single file, no extra container |
| Caddy reverse proxy with auto TLS | ✅ Done | `caddy/Caddyfile` |
| Named Docker volumes (data survives restarts) | ✅ Done | 7 volumes in compose |
| fastembed local embeddings (BAAI/bge-small-en-v1.5) | ✅ Done | Zero API cost for embeddings |
| claude-haiku-4-5-20251001 for entity extraction | ✅ Done | Prompt caching on system prompt |
| claude-sonnet-4-6 for query synthesis | ✅ Done | Streaming via Anthropic SDK |
| `POST /api/rebuild-indexes` | ✅ Done | `api/system.py` |
| `wiki_id` on all models (multi-tenancy ready) | ✅ Done | Throughout SQLite + Qdrant + Kuzu |

---

## Auth & Security

| Feature | Status | Notes |
|---|---|---|
| Owner login (password from `.env`) | ✅ Done | `api/auth.py` |
| JWT cookies (httpOnly, SameSite=Strict) | ✅ Done | 15min access / 7day refresh |
| bcrypt password hashing (cost 12) | ✅ Done | `auth.py` |
| Role-based access (owner / writer / viewer) | ✅ Done | `require_owner`, `require_writer` deps |
| Register endpoint | ✅ Done | `POST /api/auth/register` |
| Token refresh | ✅ Done | `POST /api/auth/refresh` |
| Rate limiting (login + API) | ✅ Done | `rate_limit.py` middleware |
| CSRF token protection | ✅ Done | `_CSRFProtection` middleware in `main.py` |
| Content Security Policy headers | ✅ Done | `_SecurityHeadersMiddleware` in `main.py` |
| Markdown sanitization (DOMPurify / bleach) | ✅ Done | `security/markdown.py` + DOMPurify on client |
| Non-root Docker containers | ✅ Done | `useradd app` + `USER app` in Dockerfile |

---

## Sharing & Export

| Feature | Status | Notes |
|---|---|---|
| Share links (public page token URLs) | ✅ Done | `api/share.py` + Share button in WikiPage |
| Share link management (create/list/revoke) | ✅ Done | `POST/GET/DELETE /api/share-links` |
| Share link expiry + revocation | ✅ Done | `expires_in_days` param + revoke endpoint |
| Query result sharing (frozen permalinks) | ✅ Done | `type=query` share links store frozen question, answer, and citations |
| Wiki invite (viewer / collaborator role) | ✅ Done | `api/auth.py` + SettingsPage.tsx |
| PDF export (WeasyPrint) | ✅ Done | `api/export.py` + Export dropdown in WikiPage |
| HTML export (self-contained bundle) | ✅ Done | `api/export.py` |
| Public wiki mode | ✅ Done | `PUBLIC_WIKI_ENABLED=true` exposes `/public` + `/api/public/pages` read-only |
| Cloudflare Tunnel integration | ✅ Done | README docs + read-only Caddy share subdomain routing |

---

## Week 1 KRs (from PRD §7)

| KR | Status |
|---|---|
| KR1: `docker compose up` boots with zero manual steps beyond `.env` | ✅ Done |
| KR2: Full ingest → query loop works end-to-end | ✅ Done |
| KR3: CodeMirror 6 editor with `[[wikilink]]` autocomplete functional | ✅ Done |
| KR4: MCP server passes Inspector validation and connects from Claude Code | ✅ Done — README config + Inspector `tools/list` passed for stdio/SSE |
| KR5: Graph view renders from Kuzu | ✅ Done |

---

## What to Build Next

**To close out v1:**
1. Add SSE transport smoke coverage alongside the stdio MCP smoke test
2. Broaden contradiction detection beyond deterministic enabled/disabled claims
3. Review and merge the MCP demo script and graph export test coverage through PR
