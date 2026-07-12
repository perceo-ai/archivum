# Archivum Operator Handoff

> **What this is:** A single-file runbook for any operator taking over Archivum. Covers the full loop: ingest → structured extraction → wiki → search → graph → MCP. Every command is copy-pasteable and has been tested locally.
>
> **Intended audience:** Someone who can SSH, run `docker compose`, edit `.env`, and configure an MCP client. No Python or Archivum internals required.
>
> **Last updated:** 2026-06-11
> **Build status:** Core v1 loop complete (ingest / editor / query / search / graph / MCP all working end-to-end)

---

## Table of Contents

1. [Stack Architecture (what runs where)](#1-stack-architecture)
2. [First Boot (from zero)](#2-first-boot-from-zero)
3. [Ingestion (files + URLs → wiki)](#3-ingestion)
4. [Wiki Editing & Structured Extraction](#4-wiki-editing)
5. [Semantic Search](#5-search)
6. [Graph Navigation & Export](#6-graph)
7. [MCP Access (automation / agent control)](#7-mcp-access)
8. [Maintenance & Diagnostics](#8-maintenance--diagnostics)
9. [Troubleshooting](#9-troubleshooting)
10. [Artifacts & Data Locations](#10-artifacts--data-locations)
11. [Assumptions & Manual-Only Callouts](#11-assumptions--manual-only-callouts)
12. [Handoff Checklist](#12-handoff-checklist)

---

## 1. Stack Architecture

Archivum runs as a single `docker compose` stack. No Kubernetes, no cloud dependencies (except the LLM API call itself).

```
┌────────────────────────────────────────────────────┐
│                  Caddy (reverse proxy)              │
│  :80/:443 → routes to frontend / API / WebSocket   │
│  auto-TLS if ARCHIVUM_HOST is set                  │
└────────┬───────────────────┬───────────────────────┘
         │                   │
    ┌────▼─────┐      ┌──────▼──────┐
    │ Frontend │      │   Backend   │      ┌─────────┐
    │ (nginx)  │      │  FastAPI    │      │   MCP   │
    │  :8080   │      │   :8000     │      │  :8001  │
    └──────────┘      └──┬───┬───┬──┘      │SSE/stdio│
                         │   │   │         └────┬────┘
              ┌──────────┘   │   └──────┐       │
              ▼              ▼          ▼       │
    ┌────────────┐  ┌──────────────┐  ┌──────────────┐
    │   Qdrant   │  │   SQLite(WAL)│  │  Kuzu(graph) │
    │ (vectors)  │  │  (metadata)  │  │(relationships)│
    │   :6333    │  │  /data/*.db  │  │  /data/kuzu  │
    └────────────┘  └──────────────┘  └──────────────┘
```

| Service | Technology | Port (internal) | Purpose |
|---|---|---|---|
| Caddy | Go reverse proxy | 80/443 | TLS termination, routing, security headers, CSP |
| Frontend | React + Vite → nginx | 8080 | Web UI: editor, search, graph, ingest panel |
| Backend | FastAPI (Python 3.12) | 8000 | REST API, WebSocket auto-save, ingest pipeline |
| MCP Server | Python MCP SDK | 8001 | SSE + stdio transports, 8 MCP tools |
| Qdrant | qdrant/qdrant:v1.17.1 | 6333 | Vector similarity search (embeddings) |
| Kuzu | Embedded (in backend+MCP) | — | Graph DB (nodes, edges, neighbors) |
| SQLite | WAL mode | — | Pages, ingest log, auth, share tokens |

**Key design decisions:**
- Markdown files on disk are **canonical**. Qdrant vectors and Kuzu edges are derived and fully rebuildable.
- Chose Kuzu over Neo4j to save ~2GB RAM (embedded graph DB, no separate container).
- `wiki_id` column on all data models from day 1 for future multi-tenancy.
- Default embeddings provider: `fastembed` (local, zero API cost, `BAAI/bge-small-en-v1.5`).
- Default extraction LLM: `claude-haiku-4-5-20251001` (with prompt caching). Synthesis: `claude-sonnet-4-6`.

---

## 2. First Boot (from zero)

### 2.1 Prerequisites

- Docker Engine 24+ and Docker Compose v2
- 4GB+ RAM available (Qdrant ~500MB, Kuzu ~200MB, Python ~400MB, plus overhead)
- ~2GB free disk for Docker images + volumes
- An Anthropic API key (or OpenRouter key, or local Ollama)

### 2.2 Configuration

```bash
cd /opt/archivum

# Generate secrets
JWT_SECRET=$(openssl rand -hex 32)
MCP_API_KEY=$(openssl rand -hex 24)
OWNER_PASSWORD="your-secure-password-min-12-chars"

# Create .env from template
cp .env.example .env

# Edit .env — the five must-edit values:
#   ANTHROPIC_API_KEY=sk-ant-...
#   JWT_SECRET=$JWT_SECRET
#   OWNER_PASSWORD=$OWNER_PASSWORD
#   MCP_API_KEY=$MCP_API_KEY
#   ARCHIVUM_HOST=archivum.example.com   (optional, set for TLS)

# Interactive config wizard (alternative to manual .env editing)
make setup
```

### 2.3 Boot the Stack

```bash
docker compose up -d --build
```

Wait ~15-30 seconds for health checks. Verify:

```bash
docker compose ps
# All services should show "healthy" or "running"

# Quick smoke test
curl -s http://localhost:8000/api/health | jq .
# Expected: {"status":"ok"}
```

### 2.4 Access Points

| Interface | URL | Notes |
|---|---|---|
| Web UI | `http://localhost` | Editor, search, graph, ingest |
| REST API | `http://localhost:8000` | All API endpoints |
| API docs | `http://localhost:8000/docs` | Auto-generated Swagger UI |
| MCP SSE | `http://localhost:8001/sse` | MCP clients connect here |
| Qdrant dashboard | `http://localhost:6333/dashboard` | Debug vector search directly |

### 2.5 Log In

1. Open `http://localhost` in a browser
2. Log in with username `admin` (or whatever `OWNER_USERNAME` is set to) and the `OWNER_PASSWORD` you configured
3. Session is stored in an httpOnly JWT cookie — no token to manage manually

---

## 3. Ingestion

### 3.1 What Happens During Ingest

Every source goes through the same pipeline:

```
Source (file/URL)
  → Parser extracts clean text + metadata
  → LLM produces structured output (pages, entities, relationships)
  → Markdown pages written to /data/wiki/<slug>.md
  → SQLite pages table updated
  → Qdrant vectors created (semantic search)
  → Kuzu nodes + edges created (graph relations)
```

Supported formats (all feed the same pipeline):

| Format | Extensions | Parser |
|---|---|---|
| Markdown / text | `.md`, `.txt`, `.rst` | Native with frontmatter |
| PDF | `.pdf` | PyMuPDF |
| Web pages | `.html`, `.htm`, URLs | BeautifulSoup + readability |
| Word | `.docx` | python-docx |
| PowerPoint | `.pptx` | python-pptx |
| Excel / CSV | `.xlsx`, `.xls`, `.csv` | pandas + openpyxl |
| JSON | `.json`, `.jsonl` | stdlib |
| ePub | `.epub` | ebooklib (chapters → pages) |
| Code | `.py`, `.js`, `.ts`, `.go`, `.rs`, `.sh` (+15 more) | AST-aware extraction |
| Subtitles | `.srt`, `.vtt` | Native (strips timestamps) |
| Email | `.eml` | stdlib email |

**Not yet built:** image (Claude vision), audio (Whisper), video (ffmpeg → Whisper), `.mbox`.

### 3.2 Ingest via Web UI (recommended for humans)

1. Open the UI → click the ingest panel (upload icon)
2. Drag & drop one or more files, or paste a URL
3. Watch progress stream live per file
4. On completion: list of pages created/updated with links

**Batch limit:** 20 files per drop, processed sequentially (avoids rate limits).

### 3.3 Ingest via MCP (recommended for automation)

Configure your MCP client first (see [§7 MCP Access](#7-mcp-access)), then call:

```
ingest_source(source="https://example.com/article", wiki_id="default")
ingest_source(source="/path/to/file.pdf", wiki_id="default")
```

**Manual-only callout:** The `source` path for files must be accessible from *inside* the backend container. Paths on your host machine won't work unless you copy the file into the container or use the URL/UI method. Stick to URL ingest from MCP for remote sources.

### 3.4 Ingest via REST API

```bash
# URL ingest
curl -X POST http://localhost:8000/api/ingest/url \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/article"}'

# File ingest (multipart upload)
curl -X POST http://localhost:8000/api/ingest/file \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)" \
  -F "file=@/path/to/document.pdf"
```

### 3.5 Viewing Ingest History

- Web UI: Settings → Ingest History
- API: `GET /api/ingest/history`
- SQLite directly: `docker compose exec backend sqlite3 /data/archivum.db "SELECT * FROM ingest_log ORDER BY created_at DESC LIMIT 20;"`

---

## 4. Wiki Editing

### 4.1 How the Wiki Works

- **Canonical storage:** Markdown files in `/data/wiki/*.md` on the `wiki_data` Docker volume
- **Metadata:** SQLite `pages` table (slug, title, tags, created/updated timestamps, last author)
- **Search:** Qdrant vectors generated per page
- **Graph:** Kuzu nodes per page + per entity, with auto-wired edges

### 4.2 Editing via Web UI

1. Click any page in the file tree sidebar
2. Edit in the CodeMirror 6 editor (markdown syntax highlighting, `[[wikilink]]` autocomplete)
3. Changes auto-save within **1 second** of last keystroke via WebSocket
4. Backlinks panel (right sidebar) shows all pages linking to the current page

### 4.3 Structured Extraction Outputs

When the LLM processes a source, it produces:

1. **Wiki pages** — markdown with frontmatter (title, tags, source_url, entity references)
2. **Entities** — extracted people, concepts, organizations (stored as Kuzu nodes)
3. **Relationships** — three auto-wired edge types:
   - `RELATED_TO` — from LLM-provided `relationships[]` output
   - `REFERENCES` — from `[[wikilink]]` targets inside page markdown
   - `MENTIONS` — from entity-name substring matches in page content

### 4.4 Editing via MCP

```
# Create or update a page
write_page(slug="my-page", title="My Page", content="# Hello\nWorld", wiki_id="default")

# Read a page
get_page(slug="my-page", wiki_id="default")

# List all pages
list_pages(wiki_id="default")
```

### 4.5 Creating Pages Manually

**Via UI:** Click "+" in the file tree sidebar → enter slug → start editing.

**Via API:**
```bash
curl -X PUT http://localhost:8000/api/pages/my-new-page \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"title": "My New Page", "content": "# Hello\n\nWorld"}'
```

---

## 5. Search

### 5.1 Semantic Search (Web UI)

Use the search bar (accessible from any view). Queries Qdrant vector similarity, returns ranked results with highlighted excerpts and relevance scores.

### 5.2 Search via MCP

```
search_wiki(query="what is the ingestion pipeline architecture", top_k=5, wiki_id="default")
```

Returns: `[{slug, title, excerpt, score}, ...]`

### 5.3 Search via API

```bash
curl -s "http://localhost:8000/api/search?q=ingestion+pipeline&limit=5" \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)" | jq .
```

### 5.4 Natural Language Query (LLM-synthesized)

The query feature goes beyond search — it retrieves relevant pages and synthesizes an answer with citations:

1. Open Query panel in the UI
2. Type a natural language question
3. Response streams token-by-token with clickable citations to source pages
4. "Save as page" button captures the answer back into the wiki

**Via MCP:**
```
query(question="How does Archivum handle entity extraction?", wiki_id="default")
```

**Performance expectations:**
- First token latency: < 3 seconds (with Anthropic API)
- Uses `claude-sonnet-4-6` by default for synthesis quality

---

## 6. Graph

### 6.1 Graph View (Web UI)

The graph view renders a force-directed visualization of all wiki pages and entities:
- **Nodes:** colour-coded by type (page, concept, person, organization)
- **Edges:** labelled with relationship type (REFERENCES, MENTIONS, RELATED_TO)
- **Interaction:** zoom, pan, search/highlight, click node → open wiki page

### 6.2 Graph via API

```bash
# Full graph
curl -s http://localhost:8000/api/graph | jq .

# Explicit demo graph (no DB required — health check)
curl -s http://localhost:8000/api/graph/demo | jq .

# Neighbors of a specific node
curl -s "http://localhost:8000/api/graph/neighbors?node_id=page:my-page" | jq .
```

### 6.3 Graph via MCP

```
graph_neighbors(node_id="page:my-page", wiki_id="default")
```

### 6.4 Local Mock-Safe Graph Export

Generate inspectable graph artifacts without touching the database:

```bash
make graph-export-demo
```

Writes to `graph-export-out/`:
- `graph.json` — nodes + edges as JSON
- `graph.html` — self-contained force-directed visualization (open in any browser)
- `manifest.json` — metadata about the export

**Manual-only callout:** The frontend graph endpoints (`GET /api/graph`) automatically fall back to this demo graph if the Kuzu DB export fails. This means a broken graph DB won't crash the UI — but it *will* show demo data instead of your real graph. If you see generic demo nodes ("Introduction to Archivum", "Knowledge Graph Basics"), run `make rebuild-indexes` to rebuild from real data.

---

## 7. MCP Access

Archivum exposes **8 MCP tools** through two transports, making it compatible with every major AI client.

### 7.1 Transport Compatibility

| Transport | Used by | Endpoint |
|---|---|---|
| **SSE (HTTP)** | Cursor, Windsurf, VS Code, ChatGPT, Gemini, web clients | `http://localhost:8001/sse` |
| **stdio** | Claude Desktop, Claude Code, Zed | via `docker exec -i archivum-mcp` |

### 7.2 Client Configuration (one-time setup)

Run this to print ready-to-paste config snippets:

```bash
make print-mcp-config
```

This outputs two blocks:

**Block 1 — Claude Desktop / Claude Code** (`~/.config/claude/mcp_servers.json`):
```json
{
  "archivum": {
    "command": "docker",
    "args": ["exec", "-i", "archivum-mcp", "python", "-m", "archivum.mcp.server", "--stdio"],
    "env": {"MCP_API_KEY": "<your-mcp-api-key>"}
  }
}
```

**Block 2 — Cursor / Windsurf / VS Code** (settings.json):
```json
{
  "mcpServers": {
    "archivum": {
      "url": "http://localhost:8001/sse",
      "headers": {"Authorization": "Bearer <your-mcp-api-key>"}
    }
  }
}
```

### 7.3 All 8 MCP Tools

| Tool | What it does | Key params |
|---|---|---|
| `ingest_source` | Process a file path or URL into the wiki | `source`, `wiki_id` |
| `search_wiki` | Semantic search, returns top-k with excerpts | `query`, `top_k`, `wiki_id` |
| `get_page` | Retrieve full markdown content by slug | `slug`, `wiki_id` |
| `list_pages` | List all pages, optional tag/type filter | `wiki_id` |
| `write_page` | Create or update a page and re-index | `slug`, `title`, `content`, `wiki_id` |
| `query` | Ask a natural language question — synthesized answer with citations | `question`, `wiki_id` |
| `graph_neighbors` | Return graph neighbors of a node | `node_id`, `wiki_id` |
| `lint_wiki` | Run health check — broken wikilinks, orphans | `wiki_id` |

### 7.4 MCP Validation

```bash
# Stdio transport test (inside container)
docker compose exec -T mcp python -m archivum.mcp.server --stdio <<< '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# Or use the MCP Inspector (if installed):
npx @modelcontextprotocol/inspector
```

### 7.5 MCP Auth

The MCP server uses `MCP_API_KEY` (separate from JWT user sessions). Configure it in `.env` and pass it as:
- **SSE:** `Authorization: Bearer <MCP_API_KEY>` header
- **stdio:** `MCP_API_KEY` environment variable (included automatically by `make print-mcp-config`)

---

## 8. Maintenance & Diagnostics

### 8.1 Rebuild Indexes

If search results seem stale, graph edges are missing, or you added pages manually outside the UI/MCP:

```bash
make rebuild-indexes
```

This re-derives Qdrant vectors and Kuzu edges from the canonical markdown files. Safe to run anytime — it's read-only on the markdown source.

### 8.2 Lint the Wiki

```bash
make lint-wiki
```

Detects:
- **Broken wikilinks** — `[[Page]]` links where the target page doesn't exist
- **Orphan pages** — pages with no incoming links

### 8.3 View Logs

```bash
# All services
docker compose logs -f

# Backend only (ingest errors, LLM failures, API requests)
docker compose logs -f backend

# Last 100 lines
docker compose logs --tail=100 backend
```

### 8.4 Service Health

```bash
# All container statuses
docker compose ps

# Backend health endpoint
curl -s http://localhost:8000/api/health | jq .

# Qdrant health
curl -s http://localhost:6333/readyz
# Returns: "ready"
```

### 8.5 Disk Usage

```bash
# Docker volumes (wiki data, raw files, DB)
docker system df -v | grep archivum

# Wiki page count
docker compose exec backend ls /data/wiki/ | wc -l
```

### 8.6 Backup (Manual)

Archivum stores everything on Docker volumes. To back up:

```bash
# Snapshot wiki pages (the canonical data)
docker compose exec backend tar -czf /tmp/wiki-backup-$(date +%Y%m%d).tar.gz -C /data/wiki .
docker cp archivum-backend:/tmp/wiki-backup-$(date +%Y%m%d).tar.gz ./backups/

# Or back up the entire /data directory (wiki, raw, SQLite, Kuzu)
docker compose exec backend tar -czf /tmp/archivum-full-$(date +%Y%m%d).tar.gz -C /data .
docker cp archivum-backend:/tmp/archivum-full-$(date +%Y%m%d).tar.gz ./backups/
```

**Manual-only callout:** There is no automated backup in v1. Schedule a cron job or run these commands manually before major changes.

### 8.7 Restarting

```bash
# Graceful restart (preserves data)
docker compose down
docker compose up -d --build

# Full tear-down (destroys containers, preserves volumes)
docker compose down
docker compose up -d --build

# Nuclear option (destroys everything including volumes)
docker compose down -v
```

---

## 9. Troubleshooting

### Quick Reference

| Symptom | Likely Cause | Fix |
|---|---|---|
| Search doesn't show new pages | Indexes stale after URL ingest or manual page creation | `make rebuild-indexes` |
| Graph shows demo data instead of real data | Kuzu export failed, fell back to mock graph | `make rebuild-indexes` |
| Graph edges missing | Pages referenced `[[links]]` to pages that didn't exist at ingest time | `make rebuild-indexes` |
| Ingest fails silently | LLM API key invalid or rate-limited | `docker compose logs backend \| grep -i error` |
| "Connection refused" on any port | Stack not running or port conflict | `docker compose ps`, check for other services on 80/443/8000/8001 |
| UI loads but API calls fail | Caddy routing issue or backend down | `docker compose logs caddy`, `docker compose logs backend` |
| MCP tools return auth errors | MCP_API_KEY mismatch between `.env` and client config | Run `make print-mcp-config` again and update client config |
| Qdrant healthcheck failing | Insufficient disk space or memory | `docker compose logs qdrant`, check disk: `df -h` |
| `docker compose up` fails during build | Docker daemon not running or image pull timeout | `docker info`, retry with `docker compose build --no-cache` |

### Deep Diagnostic Commands

```bash
# Check if containers are actually running
docker compose ps -a

# Inspect a specific container's resource usage
docker stats --no-stream archivum-backend

# Check backend environment variables
docker compose exec backend env | grep -E 'LLM_|EMBED_|JWT_|QDRANT_|KUZU_'

# Check if wiki data is being persisted correctly
docker compose exec backend ls -la /data/wiki/
docker compose exec backend sqlite3 /data/archivum.db "SELECT COUNT(*) FROM pages;"

# Test Qdrant directly
curl -s http://localhost:6333/collections | jq '.result.collections[] | {name, vectors_count}'

# Force Qdrant collection recreation (if dimension mismatch)
# Set QDRANT_RECREATE_COLLECTION_ON_DIM_MISMATCH=true in .env, then:
docker compose up -d backend
make rebuild-indexes
```

### Known Quirks

1. **First ingest is slow:** The first LLM call may take 5-15 seconds while the prompt cache warms up. Subsequent ingests are faster.
2. **Wikilinks are case-sensitive:** `[[My Page]]` and `[[my page]]` are different slugs.
3. **Kuzu graph is append-only:** Deleting a page from the wiki removes it from SQLite and Qdrant but may leave stale edges in Kuzu. Run `make rebuild-indexes` after bulk deletions.
4. **MCP stdio requires Docker:** The `docker exec -i archivum-mcp` approach means stdio MCP only works when the container is running.

---

## 10. Artifacts & Data Locations

### Inside Containers

| What | Path | Volume | Format |
|---|---|---|---|
| Wiki markdown pages | `/data/wiki/*.md` | `wiki_data` | Markdown with YAML frontmatter |
| Raw uploaded files | `/data/raw/*` | `raw_data` | Original files, never modified |
| Page metadata | `/data/archivum.db` | `db_data` | SQLite (WAL mode) |
| Graph DB | `/data/kuzu/` | `kuzu_data` | Kuzu embedded graph |
| Vector DB | `/qdrant/storage/` | `qdrant_data` | Qdrant (on-disk) |
| TLS certs | `/data/`, `/config/` | `caddy_data`, `caddy_config` | Caddy-managed |

### On Host (git repo)

| What | Path | Notes |
|---|---|---|
| Config | `.env` | **SECRETS — never commit** |
| Config template | `.env.example` | Safe to commit, placeholders only |
| Docker compose | `docker-compose.yml` | Single source of truth for stack |
| Caddy config | `caddy/Caddyfile` | TLS, routing, security headers, CSP |
| Backend code | `backend/archivum/` | FastAPI app, ingest pipeline, MCP server |
| Frontend code | `frontend/src/` | React + TypeScript + Vite |
| Graph export output | `graph-export-out/` | Generated by `make graph-export-demo` |
| Documentation | `docs/` | Architecture, ops, LLM notes |

### On Host (generated at runtime)

| What | Path | Notes |
|---|---|---|
| Docker volumes | `/var/lib/docker/volumes/archivum_*` | Managed by Docker, survives `docker compose down` |
| Backup directory | `./backups/` | Create this yourself before running backup commands |

---

## 11. Assumptions & Manual-Only Callouts

### Assumptions You're Inheriting

1. **Single-user deployment.** Multi-tenancy is architected (`wiki_id` on all models) but not active. There's one owner account.
2. **LAN-first access.** No Cloudflare Tunnel or public exposure configured by default. Tailscale is the intended remote access method.
3. **Markdown is canonical.** Everything derives from markdown files. If you edit SQLite, Qdrant, or Kuzu directly, your changes will be lost on the next rebuild.
4. **Last-write-wins on collisions.** No merge resolution. If two agents edit the same page simultaneously, the later write wins.
5. **Anthropic API dependency.** Out of the box, both extraction and synthesis use the Anthropic API. You can switch to OpenRouter or a local Ollama instance via `.env`.
6. **No automated backups.** Back up `/data` manually (see §8.6).
7. **Docker is the only supported deployment.** No bare-metal Python install, no systemd units.

### Manual-Only Callouts

1. **File path ingest from MCP:** Paths passed to `ingest_source` via MCP must be reachable from inside the container. Use URL ingest (which fetches over the network) or the web UI for local files — don't pass host filesystem paths to MCP ingest.

2. **Backup is manual.** See §8.6. Set a cron reminder. The canonical `wiki_data` volume is the one volume you absolutely must protect.

3. **Rate limiting not yet implemented.** The PRD specifies login rate limiting and API rate limiting — these are not built in v1. Don't expose Archivum to the public internet without Tailscale or a Cloudflare Tunnel in front of it.

4. **Markdown sanitization in progress.** The PRD's CSP and DOMPurify/bleach sanitization is partially implemented (`backend/archivum/security/markdown.py` exists). Before ingesting untrusted content (user-submitted HTML, third-party web pages), verify the sanitization path is complete.

5. **MCP Inspector validation not yet confirmed.** The 8 MCP tools exist and have been tested ad-hoc with Claude Code, but a full `@modelcontextprotocol/inspector` run has not been completed.

6. **Graph view shows demo data on fallback.** If Kuzu DB is empty or broken, the graph view silently falls back to demo fixture data. This is a feature (prevents crashes) but can be confusing — check `make rebuild-indexes` if you see demo nodes.

7. **Caddy auto-TLS requires a public hostname.** Set `ARCHIVUM_HOST` in `.env` to a real domain for HTTPS. Without it, Caddy serves HTTP only on localhost (self-signed cert for development).

---

## 12. Handoff Checklist

Before declaring the handoff complete, walk through every item:

- [ ] **Stack boots clean:** `docker compose down && docker compose up -d --build` → all services healthy in `docker compose ps`
- [ ] **Login works:** Navigate to UI, log in with owner credentials
- [ ] **Ingest works:** Ingest at least one URL and one file (drag & drop in UI)
- [ ] **Wiki visible:** New pages appear in file tree, editable in CodeMirror editor
- [ ] **Wikilinks work:** Create a page with `[[ExistingPage]]`, verify autocomplete fires, verify link navigates
- [ ] **Search works:** Search for content from the ingest, get ranked results with excerpts
- [ ] **Query works:** Ask a natural language question, get streaming answer with citations
- [ ] **Graph works:** Open graph view, see ingested nodes, click to navigate
- [ ] **MCP stdio works:** Paste config into Claude Desktop/Claude Code, run `list_pages`
- [ ] **MCP SSE works:** Paste config into Cursor/VS Code, run `search_wiki`
- [ ] **Rebuild is safe:** Run `make rebuild-indexes`, verify search + graph still work
- [ ] **Backup script tested:** Run the backup commands in §8.6, verify archive is created
- [ ] **Secrets confirmed safe:** `.env` is in `.gitignore`, no keys in chat history or logs
- [ ] **Assumptions documented:** Any host-specific setup (Tailscale IP, custom domain, Ollama endpoint) recorded below

### Host-Specific Notes (fill in during handoff)

```
Tailscale IP / hostname: ______________________
ARCHIVUM_HOST (if set): ______________________
LLM provider: Anthropic / OpenRouter / Ollama
Custom domain: ______________________
Any deviations from defaults:
______________________________________________
______________________________________________
```

---

## Quick Reference Card

```bash
# ─── Everyday Commands ───────────────────────────────────────────────

docker compose up -d --build     # Boot/rebuild stack
docker compose down              # Stop stack
docker compose logs -f backend   # Watch backend logs
docker compose ps                # Container statuses
make print-mcp-config            # Print MCP config for all clients
make rebuild-indexes             # Rebuild search + graph indexes
make lint-wiki                   # Check for broken links + orphans
make graph-export-demo           # Export graph as HTML visualization

# ─── Backup ──────────────────────────────────────────────────────────

docker compose exec backend tar -czf /tmp/wiki-backup-$(date +%Y%m%d).tar.gz -C /data/wiki .
docker cp archivum-backend:/tmp/wiki-backup-$(date +%Y%m%d).tar.gz ./backups/

# ─── Diagnostics ─────────────────────────────────────────────────────

curl -s http://localhost:8000/api/health | jq .        # Backend health
curl -s http://localhost:6333/readyz                    # Qdrant health
docker compose exec backend sqlite3 /data/archivum.db "SELECT COUNT(*) FROM pages;"  # Page count
docker system df -v | grep archivum                     # Disk usage
```
