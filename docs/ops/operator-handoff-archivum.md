# Archivum Operator Handoff

> **Self-hosted personal knowledge base.** Ingest files/URLs → structured LLM extraction → wiki editor + semantic search + knowledge graph + MCP server.
>
> **Repo:** `github.com/pranavkannepalli/archivum`
> **Local path:** `/home/claw/.openclaw/repos/archivum`

---

## Returning Operator Quick-Start

If you already have the stack set up and just need to get back into it:

```bash
cd /home/claw/.openclaw/repos/archivum

# 1) Bring it up
docker compose up -d

# 2) Quick healthcheck
docker compose ps --format 'table {{.Name}}\t{{.Status}}'

# 3) Open the UI
# → http://localhost (login with OWNER_PASSWORD from .env)
```

If the stack was down for a while, run a reindex to catch up any stale edges:

```bash
make rebuild-indexes
```

Everything below is the full reference if you need deeper operations.

---

## Prerequisites

- **Docker 24+** and **docker compose v2** installed and running
- **~5 GB disk space** for images + containers + volumes (grows with data)
- **Ports available:** 80, 443 (HTTP/HTTPS via Caddy), 8001 (MCP SSE)
- **Anthropic API key** (required — no local-only mode for extraction/synthesis)
- **OpenRouter API key** (optional, only if `LLM_*_PROVIDER=openrouter`)
- **Git** to clone and manage the repo

> ⚠️ **Manual-only callout:** The stack does **not** work without an Anthropic API key. There is no offline or local-LLM-only fallback for extraction or synthesis.

---

## Stack Services Overview

Five containers share the `archivum-net` bridge network:

| Container | Image | Role | Ports |
|-----------|-------|------|-------|
| `archivum-caddy` | `caddy:2-alpine` | Reverse proxy + auto-TLS | 80, 443 |
| `archivum-frontend` | `./frontend` (React + Vite + nginx) | Web UI | internal:8080 |
| `archivum-backend` | `./backend` (FastAPI + uvicorn) | REST API, ingest, search, graph | internal:8000 |
| `archivum-mcp` | `./backend` (Dockerfile.mcp) | MCP server (stdio + SSE) | 8001 |
| `archivum-qdrant` | `qdrant/qdrant:v1.17.1` | Vector store (semantic search) | 6333, 6334 |

Caddy proxies frontend + API traffic. The MCP container talks directly to Qdrant and shares data volumes with the backend.

### Docker Volumes (7 named volumes)

All data survives container restarts:
- `wiki_data` → `/data/wiki` — markdown pages
- `raw_data` → `/data/raw` — uploaded source files
- `db_data` → `/data` — SQLite DB (`archivum.db`)
- `kuzu_data` → `/data/kuzu` — graph store
- `qdrant_data` → `/qdrant/storage` — vector embeddings
- `caddy_data` + `caddy_config` → TLS certs + proxy config

---

## 1) Initial Setup & First Boot

From repo root:

```bash
cd /home/claw/.openclaw/repos/archivum

# 1) Create config from template
cp .env.example .env

# 2) Edit .env — fill in at minimum:
#    ANTHROPIC_API_KEY=sk-ant-...
#    JWT_SECRET=$(openssl rand -hex 32)
#    OWNER_PASSWORD=<min-12-chars>
#    MCP_API_KEY=$(openssl rand -hex 24)
#    (see .env.example for all options)

# 3) Or use the interactive wizard:
make setup

# 4) Boot the stack
docker compose up -d --build

# 5) Wait 10-15s for healthchecks, then verify
docker compose ps
```

### First Login

1. Open `http://localhost`
2. Login with username `admin` (default, set via `OWNER_USERNAME` in `.env`) and the password from `OWNER_PASSWORD`
3. On first successful login, the plaintext password is bcrypt-hashed in SQLite — the `.env` value is ignored thereafter

### URLs After Boot

| Service | URL |
|---------|-----|
| Web UI + API (via Caddy) | `http://localhost` |
| REST API (direct) | `http://localhost:8000` |
| MCP SSE | `http://localhost:8001/sse` |
| Qdrant dashboard | `http://localhost:6333/dashboard` |

### Optional: Public TLS

If you set `ARCHIVUM_HOST=archivum.madebypranav.dev` in `.env`, Caddy fetches Let's Encrypt certs and serves:
- `https://$ARCHIVUM_HOST` (UI + API)
- `https://share.$ARCHIVUM_HOST` (read-only share links)

Update the email in `caddy/Caddyfile` to match your Let's Encrypt account.

---

## 2) Ingest Pipeline

Archivum runs a single pipeline for every ingest: **parse → LLM extract → persist (SQLite + Qdrant + Kuzu)**.

### Supported File Formats

| Format | Status | Parser |
|--------|--------|--------|
| `.md`, `.txt`, `.rst` | ✅ | Native, frontmatter-aware |
| `.pdf` | ✅ | PyMuPDF |
| `.html`, `.htm` | ✅ | BeautifulSoup + readability |
| `.docx` | ✅ | python-docx |
| `.pptx` | ✅ | python-pptx |
| `.xlsx`, `.xls`, `.csv` | ✅ | pandas + openpyxl |
| `.json`, `.jsonl` | ✅ | stdlib json |
| `.epub` | ✅ | ebooklib |
| `.eml` (email) | ✅ | stdlib email |
| `.srt`, `.vtt` (transcripts) | ✅ | Native, strips timestamps |
| Code (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.sh`, +15 more) | ✅ | 20+ languages |
| Images (`.png`, `.jpg`, `.webp`) | ❌ | Claude vision — not built |
| Audio (`.mp3`, `.m4a`, `.wav`) | ❌ | Whisper — not built |
| Video (`.mp4`, `.mov`) | ❌ | ffmpeg → Whisper — not built |
| `.mbox` | ❌ | Not implemented |

### Ingest via MCP (Recommended)

1) Configure your MCP client:
```bash
make print-mcp-config
```
Paste the output into your Claude Desktop / Claude Code / Cursor config.

2) Use the MCP tool:
```
ingest_source(source="https://example.com/article", wiki_id="default")
```

**What `source` accepts:**
- **URLs** — work directly (HTTP/HTTPS)
- **File paths** — must be reachable from inside the MCP container. Local host paths (e.g., `/home/claw/foo.pdf`) generally won't work unless volume-mounted. **Prefer URLs** or copy files to a container-accessible location.

### Ingest via Web UI

1. Open `http://localhost/ingest`
2. Drag-and-drop files or paste URLs
3. Watch SSE progress stream per file
4. New pages appear in the file tree sidebar

### Ingest via REST API (Advanced)

```bash
# URL ingest
curl -X POST http://localhost:8000/api/ingest/url \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your-jwt>" \
  -d '{"url": "https://example.com/article", "wiki_id": "default"}'

# File ingest
curl -X POST http://localhost:8000/api/ingest/file \
  -H "Authorization: Bearer <your-jwt>" \
  -F "file=@document.pdf" \
  -F "wiki_id=default"

# Batch ingest (up to 20 files)
curl -X POST http://localhost:8000/api/ingest/batch \
  -H "Authorization: Bearer <your-jwt>" \
  -F "files=@doc1.pdf" -F "files=@doc2.md" \
  -F "wiki_id=default"
```

> ⚠️ **Manual-only callout:** REST API ingest endpoints require an authenticated writer session (JWT). If you don't have a tested auth flow outside the UI, use the UI or MCP instead.

### What Ingest Produces

Each ingest run produces:
1. **Wiki pages** — markdown files at `/data/wiki/<slug>.md` + SQLite `pages` table
2. **Entities** — `(:Entity {name, type})` nodes in Kuzu
3. **Graph edges** (auto-wired):
   - `RELATED_TO` → from LLM-provided `relationships[]` (Entity ↔ Entity)
   - `REFERENCES` → from `[[wikilink]]` syntax in generated markdown (Page ↔ Page)
   - `MENTIONS` → from entity-name substring matches in page content (Page ↔ Entity)

### Key Ingest Limitation

`REFERENCES` edges are **ingest-time only**. If page B references page A via `[[wikilink]]` but page A doesn't exist yet, the edge won't be created. **Run `make rebuild-indexes` after batch ingests** to catch cross-references.

---

## 3) Wiki Editing

### Web UI Editor

- **CodeMirror 6** with markdown syntax highlighting
- `[[wikilink]]` autocomplete — shows existing pages as you type
- **Broken wikilink detection** — red underline for non-existent targets
- **Auto-save** — debounced 1s, saves via `PUT /api/pages/:slug`
- **Backlinks panel** — shows which pages link to the current page
- **File tree sidebar** — create/delete/rename pages
- **Tags** — editable per page, shown in metadata bar

### Programmatic: MCP Tools

```
write_page(title="My Page", content="# Hello\n\nWorld.", slug="my-page")
get_page(slug="my-page", wiki_id="default")
list_pages(wiki_id="default")
```

### Lint Wiki

Finds broken wikilinks and orphan pages:

```bash
make lint-wiki
# or via MCP: lint_wiki(wiki_id="default")
```

---

## 4) Semantic Search

### Web UI

Use the search bar (`/search`). Queries Qdrant vector store with chunk embeddings.

### MCP Tool

```
search_wiki(query="graph databases", top_k=5, wiki_id="default")
```

Returns: `slug`, `title`, `excerpt`, `score`

### Programmatic

```bash
curl -s http://localhost:8000/api/search \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)" \
  -H "Content-Type: application/json" \
  -d '{"query": "kubernetes pods", "wiki_id": "default", "top_k": 10}' | jq .
```

---

## 5) Knowledge Graph

### Web UI

Navigate to `/graph` for an interactive force-directed graph (vis-network):
- Nodes color-coded by type (Page/Entity)
- Edges labeled by relationship type
- Click any node → navigates to that wiki page
- Zoom, pan, search, highlight

### REST API

```bash
# Full graph (DB-backed, falls back to demo if Kuzu fails)
curl -s http://localhost:8000/api/graph \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)" | jq .

# Explicit demo graph (no DB required)
curl -s http://localhost:8000/api/graph/demo \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)" | jq .
```

### MCP Tool

```
graph_neighbors(node_id="page:my-slug", wiki_id="default")
```

### Local Graph Export (Mock-Safe Demo)

```bash
make graph-export-demo
```

Writes to `graph-export-out/`:
- `graph.json` — raw nodes + edges
- `graph.html` — self-contained interactive visualization
- `manifest.json` — metadata

Open with: `xdg-open graph-export-out/graph.html`

---

## 6) AI Query (RAG)

### Web UI

Navigate to `/query`. Type a question → streaming SSE response with citations linked to source pages. You can save any answer as a wiki page.

### MCP Tool

```
query(question="What is the retention policy for backups?", wiki_id="default")
```

### How It Works

1. Semantic retrieval via Qdrant over chunk embeddings (sliding window)
2. Top-N hits deduplicated by page slug
3. Only excerpts (not full pages) are included in the Claude synthesis prompt
4. Response is streamed token-by-token with citations

---

## 7) MCP Server — Full Reference

Archivum exposes an MCP server in two transports (same tools):

| Transport | URL/Command | Use Case |
|-----------|------------|----------|
| **SSE** (HTTP) | `http://localhost:8001/sse` | Cursor, VS Code, Windsurf |
| **stdio** (in-container) | `docker exec -i archivum-mcp python -m archivum.mcp.server --stdio` | Claude Desktop, Claude Code |

### Client Config (one command)

```bash
make print-mcp-config
```

### All MCP Tools

| Tool | Signature | What It Does |
|------|-----------|--------------|
| `ingest_source` | `(source, wiki_id)` | Runs full ingest pipeline for URL or path |
| `search_wiki` | `(query, top_k, wiki_id)` | Semantic search returning ranked excerpts |
| `list_pages` | `(wiki_id)` | Lists all pages in SQLite |
| `get_page` | `(slug, wiki_id)` | Returns full markdown content |
| `write_page` | `(title, content, slug?, tags?, wiki_id)` | Create or update + re-index |
| `query` | `(question, wiki_id)` | RAG synthesis with citations |
| `graph_neighbors` | `(node_id, wiki_id)` | 1-hop Kuzu neighbors |
| `lint_wiki` | `(wiki_id)` | Broken wiklinks + orphan pages |

### Debugging MCP (stdio)

```bash
docker compose exec -T mcp python -m archivum.mcp.server --stdio
```

---

## 8) Auth & User Management

### Auth Flow

- **Owner login:** `POST /api/auth/login` with username + password → httpOnly JWT cookie (15min access / 7day refresh)
- **Password hashing:** bcrypt (cost 12), hashed on first successful login
- **Roles:** `owner`, `writer`, `viewer` — enforced by FastAPI dependency injection
- **Register:** `POST /api/auth/register` for creating additional users
- **Token refresh:** `POST /api/auth/refresh` (cookie-based)

### Changing the Owner Password

Option A — via SQLite (if you know the DB path):
```bash
# Generate new bcrypt hash
python3 -c "import bcrypt; print(bcrypt.hashpw(b'newpassword', bcrypt.gensalt(12)).decode())"

# Update in SQLite
docker compose exec backend sqlite3 /data/archivum.db \
  "UPDATE users SET password_hash='<hash-from-above>' WHERE username='admin';"
```

Option B — wipe and re-create:
```bash
docker compose down -v    # ⚠️ Destructive — removes all data
cp .env.example .env
# edit .env with new OWNER_PASSWORD
docker compose up -d --build
# Login; password will be hashed on first use
```

> ⚠️ **Manual-only callout:** Changing `OWNER_PASSWORD` in `.env` after first login has **no effect**. The hash in SQLite takes precedence.

### Security Gaps (Not Yet Built)

These are known gaps per Progress.md:
- ❌ Markdown sanitization (DOMPurify/bleach) — **critical before exposing to untrusted content**
- ❌ Rate limiting (login brute-force protection)
- ❌ CSRF token protection
- ❌ Content Security Policy headers
- ❓ Non-root Docker containers (unconfirmed)

---

## 9) Maintenance

### Rebuild Indexes

After batch ingests, or if graph edges seem stale:

```bash
make rebuild-indexes
```

This re-initializes Qdrant + Kuzu Page nodes and rebuilds `REFERENCES` edges by scanning `[[wikilink]]` in all stored page content.

### View Logs

```bash
docker compose logs -f backend      # ingest/API logs
docker compose logs -f frontend     # Vite/build logs
docker compose logs -f mcp          # MCP connection logs
docker compose logs -f qdrant       # vector store logs
docker compose logs -f caddy        # access logs, TLS, proxy errors
```

### Health Checks

```bash
# All containers
docker compose ps --format 'table {{.Name}}\t{{.Status}}'

# Backend health
curl -s http://localhost/api/health | jq .

# Qdrant readiness
curl -s http://localhost:6333/readyz

# MCP SSE endpoint (will hang open — that's expected)
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/sse
# Expected: 200

# Caddy / frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# Expected: 200
```

---

## 10) Backup & Restore

### Backup All Data

```bash
cd /home/claw/.openclaw/repos/archivum
BACKUP_DIR="./backups/$(date +%Y-%m-%d)"

mkdir -p "$BACKUP_DIR"

# Wiki pages (markdown)
docker run --rm \
  -v archivum_wiki_data:/data \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar czf /backup/wiki.tar.gz -C /data .

# Raw uploads
docker run --rm \
  -v archivum_raw_data:/data \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar czf /backup/raw.tar.gz -C /data .

# SQLite + Kuzu
docker run --rm \
  -v archivum_db_data:/data \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine tar czf /backup/db.tar.gz -C /data .

# Also copy .env for reference
cp .env "$BACKUP_DIR/.env.bak"

echo "Backup complete: $BACKUP_DIR"
```

### Restore From Backup

```bash
cd /home/claw/.openclaw/repos/archivum
BACKUP_DIR="./backups/2026-06-10"  # adjust date

# Stop the stack
docker compose down

# Restore data volumes
docker run --rm \
  -v archivum_wiki_data:/data \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/wiki.tar.gz -C /data"

docker run --rm \
  -v archivum_raw_data:/data \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/raw.tar.gz -C /data"

docker run --rm \
  -v archivum_db_data:/data \
  -v "$(pwd)/$BACKUP_DIR":/backup \
  alpine sh -c "rm -rf /data/* && tar xzf /backup/db.tar.gz -C /data"

# Restore .env if needed
cp "$BACKUP_DIR/.env.bak" .env

# Bring back up
docker compose up -d --build
```

---

## 11) Database Inspection

### SQLite (Pages, Users, Ingest Logs)

```bash
# Open SQLite shell
docker compose exec backend sqlite3 /data/archivum.db

# Useful queries:
.tables                          # list all tables
.schema pages                    # page table schema
SELECT slug, title, updated_at FROM pages ORDER BY updated_at DESC LIMIT 10;
SELECT * FROM ingest_log ORDER BY created_at DESC LIMIT 5;
SELECT username, role FROM users;
```

### Kuzu (Graph)

```bash
# Open Kuzu shell
docker compose exec backend python3 -c "
import kuzu
db = kuzu.Database('/data/kuzu')
conn = kuzu.Connection(db)
print('Nodes:', conn.execute('MATCH (n) RETURN count(n)').get_next())
print('Edges:', conn.execute('MATCH ()-[r]->() RETURN count(r)').get_next())
"
```

### Qdrant (Vectors)

Open `http://localhost:6333/dashboard` in a browser, or:

```bash
# List collections
curl -s http://localhost:6333/collections | jq .

# Collection info
curl -s http://localhost:6333/collections/archivum_pages | jq .
```

---

## 12) Upgrading the Stack

```bash
cd /home/claw/.openclaw/repos/archivum

# 1) Pull latest code
git pull origin main

# 2) Check for new .env variables (compare .env.example to your .env)
diff .env.example .env
# Add any new required vars to your .env

# 3) Backup (see Section 10)

# 4) Rebuild and restart
docker compose down
docker compose up -d --build

# 5) Verify
docker compose ps
make rebuild-indexes   # refresh indexes after schema changes
```

---

## 13) Full Reset & Cleanup

### Soft Reset (Restart Everything)

```bash
docker compose down && docker compose up -d --build
```

### Hard Reset (Wipe All Data)

```bash
# ⚠️ DESTRUCTIVE — deletes ALL pages, vectors, graph, and uploads
docker compose down -v
docker volume ls | grep archivum_ | awk '{print $2}' | xargs -r docker volume rm
cp .env.example .env
# Re-edit .env with your keys
docker compose up -d --build
```

> ⚠️ **Manual-only callout:** Hard reset is irreversible. No automatic backup is created. Always run a backup first (Section 10).

---

## 14) Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Search doesn't show new pages | Indexes stale | `make rebuild-indexes` |
| Graph edges missing (references) | Target page didn't exist at ingest time | `make rebuild-indexes` |
| Graph edges missing (entities) | LLM didn't extract relationships | Re-ingest the source |
| Graph view errors / blank | Kuzu DB issue | Try `make graph-export-demo` to isolate; check `docker compose logs backend` |
| Ingest fails / 500 | Invalid source URL/path | Check `docker compose logs backend`; verify URL is accessible |
| Ingest returns empty pages | LLM rate-limited or API key invalid | Check Anthropic API key in `.env`; verify billing/rate limits |
| `ingest_source` from MCP fails with file path | File not reachable from container | Use URLs instead, or volume-mount the directory |
| MCP client won't connect (stdio) | Container not running | `docker compose ps` — confirm `archivum-mcp` is up |
| MCP client won't connect (SSE) | Port conflict or firewall | Check `curl http://localhost:8001/sse` returns 200 |
| Login redirects to /login after boot | Auth token stale or OWNER_PASSWORD changed | Clear cookies; re-login with current password from SQLite |
| Password in `.env` ignored after first login | Password hashed in SQLite on first use | See Section 8 for password reset |
| Stack won't start / port conflict | Port 80/443/8001 in use | `sudo lsof -i :80 :443 :8001` — stop conflicting services |
| Caddy TLS errors | `ARCHIVUM_HOST` set but DNS/port 443 not reachable | Unset `ARCHIVUM_HOST` for localhost-only, or verify DNS |
| Qdrant dimension mismatch after model change | Embedding model changed | Set `QDRANT_RECREATE_COLLECTION_ON_DIM_MISMATCH=true` and reboot |
| Backend crashes with OOM | Insufficient RAM for model + embeddings | Increase Docker memory limit; switch to smaller embed model |
| Frontend shows "Loading..." forever | Backend unreachable or auth failure | Check `docker compose logs backend`; verify Caddy is proxying correctly |

---

## 15) Codebase Navigation (For Debugging/Extending)

```
backend/archivum/
├── main.py              # FastAPI app entry point
├── config.py            # All env-var config (check here for new settings)
├── auth.py              # JWT auth, bcrypt hashing, session management
├── api/                 # REST endpoint routers
├── ingest/              # Parsers, LLM extraction agent, orchestration pipeline
│   ├── parsers.py       # File/URL → ParsedDoc (20+ formats)
│   ├── agent.py         # Claude → pages[] + entities[] + relationships[]
│   └── pipeline.py      # Orchestrates parse → extract → persist
├── db/                  # All persistence layers
│   ├── sqlite.py        # Pages table, ingest logs, users
│   ├── qdrant_client.py # Chunk embedding + vector upsert
│   └── graph.py         # Kuzu: Page/Entity nodes + edges
├── llm/                 # LLM provider adapter (Anthropic, OpenAI compat, OpenRouter)
├── mcp/                 # MCP server — tool definitions + transport (stdio/SSE)
│   └── server.py        # All MCP tools live here
├── scripts/             # Utility scripts (graph_export, etc.)
├── cli_config.py        # CLI setup wizard (via setup.sh)
└── security/            # CSP, rate limiting, observability

frontend/src/
├── App.tsx              # React Router (wiki, graph, query, ingest, search)
├── components/
│   ├── Editor/          # CodeMirror 6 editor + wikilink autocomplete
│   ├── FileTree.tsx     # Sidebar page tree (create/delete)
│   ├── GraphView.tsx    # Force-directed vis-network graph
│   ├── IngestPanel.tsx   # Drag-and-drop ingest UI
│   ├── QueryPanel.tsx   # Streaming SSE RAG query
│   ├── SearchBar.tsx    # Semantic search
│   └── BacklinksPanel.tsx # Backlinks display
├── api.ts               # Frontend API client
├── store.ts             # Zustand state management
└── types.ts             # TypeScript interfaces (Page, SearchResult, GraphNode, etc.)
```

---

## 16) Key Assumptions

1. **Anthropic API is the primary LLM provider.** Extraction (haiku) and synthesis (sonnet) require an Anthropic key. OpenRouter is supported as an alternative but not the default.
2. **Local embeddings (fastembed) run inside the backend container.** No external embedding service needed unless explicitly configured.
3. **File ingestion from MCP is container-relative.** Local host paths are not accessible from inside Docker containers unless volume-mounted.
4. **`REFERENCES` edges are ingest-time only.** Cross-references between pages only resolve if the target exists at ingest time. Run `make rebuild-indexes` afterward.
5. **First boot hashes the owner password.** Plaintext in `.env` is read once, hashed, and stored in SQLite. The `.env` value is ignored thereafter.
6. **Caddy auto-generates self-signed certs** when `ARCHIVUM_HOST` is unset (localhost-only). For production, set `ARCHIVUM_HOST` for automatic Let's Encrypt.
7. **Qdrant collection dimensions must match the embedding model.** Use `QDRANT_RECREATE_COLLECTION_ON_DIM_MISMATCH=true` if you change models.
8. **Query-time context is limited to retrieval excerpts.** Claude never sees full page contents during queries — only the top-N Qdrant chunks after deduplication.
9. **The stack is single-user/multi-role.** Multiple users can be registered but there's no multi-tenant isolation beyond `wiki_id`.

---

## 17) Done Checklist (Pre-Handoff Verification)

Before handing off to another operator, verify:

- [ ] Stack boots clean: `docker compose up -d --build`
- [ ] All 5 services healthy: `docker compose ps` shows all `Up`/`healthy`
- [ ] Web UI loads: `curl -s -o /dev/null -w "%{http_code}" http://localhost/` → `200`
- [ ] Login works: open browser, log in with `OWNER_PASSWORD`
- [ ] At least one ingest completes successfully (via MCP or UI)
- [ ] New content is visible in the file tree and searchable
- [ ] Graph view shows expected neighbors for ingested content
- [ ] MCP client connects (test with `make print-mcp-config` → paste → verify tools load)
- [ ] Backup procedure documented/executed (Section 10)
- [ ] Any special assumptions about file paths or API keys recorded here: _______________

---

## Further Reading

| Document | Path | Topic |
|----------|------|-------|
| Ingest pipeline deep-dive | `../architecture/ingest.md` | Parse → extract → persist flow |
| Graph model (Kuzu) | `../architecture/graph-model.md` | Node/edge types and relationships |
| MCP server tool reference | `../architecture/mcp.md` | Tool signatures and behavior |
| Retrieval + context sizing | `../architecture/retrieval.md` | How RAG limits context to Qdrant excerpts |
| Claude/LLM notes | `../llm/claude.md` | Prompt caching, model selection |
| Product requirements (PRD) | `../prd/archivum-prd-v1.0.md` | Full feature spec |
| Build progress | `../project/progress.md` | Feature completion status |
| OpenClaw cron management | `./openclaw-cron-management-runbook.md` | Scheduling maintenance jobs |
