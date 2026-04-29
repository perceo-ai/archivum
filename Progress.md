# Archivum — Build Progress

_Last updated: 2026-04-28_

---

## Overall Status

**Core v1 loop: COMPLETE** — ingest → wiki → query → MCP all working end-to-end.  
**Remaining:** stretch parsers (image/audio/video), security hardening, share links, export.

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
| Parser: images (`.png`, `.jpg`, `.webp`) — Claude vision | ❌ Not built | PRD Day 7 stretch |
| Parser: audio (`.mp3`, `.m4a`, `.wav`) — Whisper | ❌ Not built | PRD Day 7 stretch |
| Parser: video (`.mp4`, `.mov`) — ffmpeg → Whisper | ❌ Not built | PRD Day 7 stretch |
| Parser: `.mbox` | ❌ Not built | PRD listed, not implemented |

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
| MCP Inspector validation | ❌ Not confirmed | Needs manual run |
| Client config snippets in README | ❌ Not built | README not written yet |

---

## Epic 7: Lint

| Feature | Status | Notes |
|---|---|---|
| Broken wikilink detection | ✅ Done | `GET /api/lint` + MCP `lint_wiki` |
| Orphan page detection | ✅ Done | Same endpoints |
| One-click fix UI | ❌ Not built | PRD P1 — UI not wired |
| Contradiction detection | ❌ Not built | PRD listed, not implemented |

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
| Rate limiting (login + API) | ❌ Not built | PRD security hardening |
| CSRF token protection | ❌ Not built | PRD security hardening |
| Content Security Policy headers | ❌ Not built | PRD security hardening |
| Markdown sanitization (DOMPurify / bleach) | ❌ Not built | PRD security hardening — **critical** |
| Non-root Docker containers | ❌ Not confirmed | Check Dockerfiles |

---

## Sharing & Export

| Feature | Status | Notes |
|---|---|---|
| Share links (public page token URLs) | ❌ Not built | PRD Epic 11 |
| Query result sharing (frozen permalinks) | ❌ Not built | PRD Epic 11 |
| Share link expiry + revocation | ❌ Not built | PRD Epic 11 |
| Wiki invite (viewer / collaborator role) | ❌ Not built | PRD Epic 11 |
| PDF export (WeasyPrint) | ❌ Not built | PRD Epic 11 |
| HTML export (self-contained bundle) | ❌ Not built | PRD Epic 11 |
| Public wiki mode | ❌ Not built | PRD Epic 11 |
| Cloudflare Tunnel integration | ❌ Not built | PRD Section 10 |

---

## Week 1 KRs (from PRD §7)

| KR | Status |
|---|---|
| KR1: `docker compose up` boots with zero manual steps beyond `.env` | ✅ Done |
| KR2: Full ingest → query loop works end-to-end | ✅ Done |
| KR3: CodeMirror 6 editor with `[[wikilink]]` autocomplete functional | ✅ Done |
| KR4: MCP server connects from Claude Code (Inspector validation pending) | 🟡 Partial |
| KR5: Graph view renders from Kuzu | ✅ Done |

---

## What to Build Next

**Highest leverage (unblocking daily use):**
1. Markdown sanitization — security gap before real content goes in
2. Rate limiting — login brute-force protection
3. MCP Inspector validation run — confirm KR4 complete
4. README with client config snippets — needed for KR4 to count

**Medium priority:**
5. Share links — needed before showing anyone else
6. Image ingest (Claude vision) — high-value parser gap
7. Keyword search fallback — confirm wired or add it

**Lower priority / cut candidates:**
8. Audio/video ingest (Whisper + ffmpeg) — stretch
9. PDF/HTML export
10. Wiki invite flow
11. One-click lint fixes UI
