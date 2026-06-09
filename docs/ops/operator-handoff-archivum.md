# Archivum operator handoff (ingest → extract → wiki/search/graph → MCP)

## Goal
Give the next operator a repeatable, *local* runbook for:
- personal knowledge ingestion (files + URLs)
- structured extraction (LLM → pages + entities/relationships)
- wiki editing + semantic search
- graph browsing + graph export
- MCP access (for automation / Claude Desktop)

## Safety notes (read first)
- **Secrets live in `.env`**. Don’t paste keys into chat/logs.
- **Prefer UI / MCP for ingest/edit**. Avoid authenticated `curl` calls unless you explicitly need them.
- If something looks “stale” (search results / graph edges), run the maintenance steps in **Reindex / rebuild**.

## Where things live (important paths)
Inside the Docker containers:
- Wiki markdown pages: **`/data/wiki`** (disk)
- Raw uploads: **`/data/raw`** (disk)
- SQLite DB (pages + ingest logs): **`/data/archivum.db`**
- Kuzu graph store: **`/data/kuzu`**

These are persisted as Docker volumes via `docker-compose.yml` (`wiki_data`, `raw_data`, `db_data`, `kuzu_data`).

## 0) Start / validate the stack
From repo root (`/home/claw/.openclaw/repos/archivum`):

1) Create config if needed
```bash
cp .env.example .env
# edit .env (API keys, JWT_SECRET, OWNER_PASSWORD, MCP_API_KEY, etc.)
```

2) Boot
```bash
docker compose up -d --build
```

3) Check logs (backend)
```bash
docker compose logs -f backend
```

Expected URLs (local):
- Web UI: http://localhost
- REST API: http://localhost:8000
- MCP SSE: http://localhost:8001/sse

## 1) Ingest (files + URLs)
Archivum ingestion runs a single pipeline that:
- parses the source
- uses an LLM to produce markdown pages + entities/relationships
- writes pages to the wiki directory + persists to SQLite/Qdrant/Kuzu

### Recommended: ingest via MCP (Claude Desktop / automation)
1) Configure your MCP client (fastest path):
```bash
make print-mcp-config
```
Then paste the printed JSON into Claude Desktop / Claude Code / Cursor.

2) Use the MCP tool:
- `ingest_source(source, wiki_id)`

What to pass as `source`:
- **URL**: works directly (e.g. `https://...`)
- **File path**: works only if the path is reachable *from the backend container environment* (local path access depends on your setup). If unsure, ingest by **URL** or put files where the container can read them.

What you should see after ingest:
- New/updated markdown files appear under `/data/wiki/<slug>.md`
- Search and graph reflect the new content after indexes are updated (see **2) Reindex / rebuild**).

### Advanced (REST API): `/api/ingest/*`
If you need API-driven ingest, use:
- `POST /api/ingest/file`
- `POST /api/ingest/url`
- `POST /api/ingest/batch`

**Manual-only callout:** these endpoints require an authenticated writer session. If you don’t already have a tested auth approach, use the UI or MCP instead.

## 2) Wiki editing + structured extraction outputs
### What ingestion produces
- **Wiki pages**: markdown pages (slug/title/content/tags)
- **Graph edges** (auto-wired):
  - `RELATED_TO`: from LLM-provided `relationships[]`
  - `REFERENCES`: from `[[wikilink]]` targets inside generated page markdown
  - `MENTIONS`: from entity-name substring matches in page content

### Editing wiki pages (recommended: UI)
Use the web UI to create/update pages. Under the hood, the app updates:
- markdown content in `/data/wiki/*.md`
- SQLite `pages` table
- Qdrant vectors (semantic search)
- Kuzu nodes/edges

### Maintenance: rebuild / reindex
If you suspect edges (especially `REFERENCES`) didn’t connect because pages didn’t exist at ingest time, rebuild.

1) Run (includes an auth header using `MCP_API_KEY`):
```bash
make rebuild-indexes
```

2) Then verify quickly:
- search for newly referenced pages
- open graph view and confirm expected neighbor edges

### Lint wiki for broken wikilinks (optional)
```bash
make lint-wiki
```

## 3) Search (wiki)
### Recommended: web UI
Use the UI’s semantic search. It queries Qdrant and falls back to keyword/FTS when needed.

### Programmatic: MCP tool
Use the MCP tool:
- `search_wiki(query, top_k, wiki_id)`

Expected output items:
- `slug`, `title`, `excerpt`, `score`

## 4) Graph (neighbors / browsing)
### Recommended: web UI
Use the graph view to browse nodes and 1-hop edges.

### Programmatic: REST API (graph)
Endpoints:
- `GET /api/graph` (DB-backed with a mock-safe fallback)
- `GET /api/graph/demo` (explicit demo graph)

### Programmatic: MCP tool
Use the MCP tool:
- `graph_neighbors(node_id, wiki_id)`

### Local mock-safe graph export
Generate inspectable artifacts (no DB required):
```bash
make graph-export-demo
```
Writes:
- `graph-export-out/graph.json`
- `graph-export-out/graph.html`
- `graph-export-out/manifest.json`

## 5) MCP access details (what to tell the next operator)
Archivum MCP tools are implemented in `backend/archivum/mcp/server.py`.

1) Tooling summary (high level):
- `ingest_source`
- `search_wiki`
- `list_pages`
- `get_page`
- `write_page`
- `query`
- `graph_neighbors`
- `lint_wiki`

2) Stdio debugging (optional; advanced operators)
Run the MCP server in a container for debugging:
```bash
docker compose exec -T mcp python -m archivum.mcp.server --stdio
```

## Troubleshooting quick hits
- **Search doesn’t show new pages**: rebuild/reindex (`make rebuild-indexes`).
- **Graph edges missing (especially references)**: rebuild/reindex; ensure wikilinks `[[like this]]` are correct.
- **Graph view errors**: try `make graph-export-demo` to confirm the frontend/fixtures path is healthy.
- **Ingest pipeline errors**: check backend logs (`docker compose logs -f backend`) and confirm the source URL/path is reachable.

## “Done” checklist (handoff)
Before handing off:
- Stack starts (`docker compose up -d --build`)
- At least one ingest completed successfully (via MCP tool)
- New content is visible in wiki/search
- Graph view shows expected neighbors for that content
- You recorded any special assumptions about file ingestion paths
