# Archivum operator handoff (ingest → extract → wiki/search/graph → MCP)

## Goal
Give the next operator a repeatable, *local* runbook for:
- personal knowledge ingestion (files + URLs)
- structured extraction (LLM → pages + entities/relationships)
- wiki editing + semantic search
- graph browsing + graph export
- MCP access (for automation / Claude Desktop)

## Prerequisites (what you need before starting)

- **Docker 24+** and **docker compose v2** installed and running
- **~5 GB disk space** for images, containers, and volumes (grows with data)
- **Ports available**: 80, 443 (HTTP/HTTPS), 8001 (MCP SSE)
- **Anthropic API key** (required for extraction/synthesis — no local-only mode)
- **OpenRouter API key** (optional, only if `LLM_*_PROVIDER=openrouter`)
- **Git** to clone and manage the repo

> **Manual-only callout:** The stack does *not* work without an Anthropic API key. There is no offline or local-LLM-only mode for extraction/synthesis.

## Stack services overview (docker compose)

Five containers run the system:

| Container | Image/Source | Role | Ports |
|-----------|-------------|------|-------|
| `archivum-caddy` | `caddy:2-alpine` | Reverse proxy + auto-TLS | 80, 443 |
| `archivum-frontend` | `./frontend` (Vite/React) | Web UI | internal:8080 |
| `archivum-backend` | `./backend` (FastAPI + uvicorn) | REST API, ingest, search, graph | internal:8000 |
| `archivum-mcp` | `./backend` (Dockerfile.mcp) | MCP server (stdio + SSE) | 8001 |
| `archivum-qdrant` | `qdrant/qdrant:v1.17.1` | Vector store (semantic search) | 6333, 6334 |

All services share the `archivum-net` bridge network. Caddy proxies frontend and API traffic; the MCP container talks directly to Qdrant and shares data volumes with the backend.

## Safety notes (read first)
- **Secrets live in `.env`**. Don't paste keys into chat/logs.
- **Prefer UI / MCP for ingest/edit**. Avoid authenticated `curl` calls unless you explicitly need them.
- If something looks "stale" (search results / graph edges), run the maintenance steps in **Reindex / rebuild**.

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

**Manual-only callout:** these endpoints require an authenticated writer session. If you don't already have a tested auth approach, use the UI or MCP instead.

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
If you suspect edges (especially `REFERENCES`) didn't connect because pages didn't exist at ingest time, rebuild.

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
Use the UI's semantic search. It queries Qdrant and falls back to keyword/FTS when needed.

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

## Health checks & per-service validation

### Quick all-in-one
```bash
# Are all containers running?
docker compose ps

# Are all 5 services healthy?
docker compose ps --format 'table {{.Name}}\t{{.Status}}'
```

### Individual service checks
```bash
# Backend health endpoint
curl -s http://localhost/api/health | jq .

# Qdrant readiness
curl -s http://localhost:6333/readyz
# Expected: "all shards are ready" (or HTTP 200 + valid response)

# Caddy (proxy)
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# Expected: 200

# Frontend (via Caddy)
curl -s -o /dev/null -w "%{http_code}" http://localhost/
# Expected: 200

# MCP SSE endpoint
curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/sse
# Expected: 200 (it stays open; cancel after confirming)
```

### View logs per service
```bash
docker compose logs -f backend      # ingest/API logs
docker compose logs -f frontend     # Vite dev/build logs
docker compose logs -f mcp          # MCP connection logs
docker compose logs -f qdrant       # vector store logs
docker compose logs -f caddy        # access logs, TLS, proxy errors
```

## Full reset / cleanup

### Soft reset (restart everything)
```bash
docker compose down && docker compose up -d --build
```

### Hard reset (wipe all data, start fresh)
```bash
# ⚠️ Destructive — deletes ALL wiki pages, vectors, and graph data
docker compose down -v
# Remove any orphan volumes
docker volume ls | grep archivum_ | awk '{print $2}' | xargs -r docker volume rm
# Optional: reset .env to defaults
cp .env.example .env
# Reboot
docker compose up -d --build
```

> **Manual-only callout:** The hard reset is irreversible. No backup is created automatically. Consider backing up the Docker volumes first if you need to preserve anything (`docker run --rm -v archivum_wiki_data:/data -v $(pwd)/backup:/backup alpine tar czf /backup/wiki-backup.tar.gz -C /data .`).

## Troubleshooting quick hits
- **Search doesn't show new pages**: rebuild/reindex (`make rebuild-indexes`).
- **Graph edges missing (especially references)**: rebuild/reindex; ensure wikilinks `[[like this]]` are correct.
- **Graph view errors**: try `make graph-export-demo` to confirm the frontend/fixtures path is healthy.
- **Ingest pipeline errors**: check backend logs (`docker compose logs -f backend`) and confirm the source URL/path is reachable.

## Backend code navigation (for debugging / extending)

Key directories for understanding and modifying behavior:

```
backend/archivum/
├── main.py              # FastAPI app entry point
├── config.py            # All env-var config (check here for new settings)
├── auth.py              # JWT auth + session management
├── api/                 # REST endpoint routers
├── ingest/              # Parsers, LLM extraction agent, orchestration pipeline
│   ├── parsers.py       # File/URL → ParsedDoc
│   ├── agent.py         # Claude → pages[] + entities[] + relationships[]
│   └── pipeline.py      # Orchestrates parse → extract → persist
├── db/                  # All persistence layers
│   ├── sqlite.py        # Pages table, ingest logs
│   ├── qdrant_client.py # Chunk embedding + vector upsert
│   └── graph.py         # Kuzu: Page/Entity nodes + edges
├── llm/                 # LLM provider adapter (Anthropic, OpenAI compat, OpenRouter)
├── mcp/                 # MCP server — tool definitions + transport (stdio/SSE)
│   └── server.py        # All MCP tools live here
├── scripts/             # Utility scripts (graph_export, etc.)
├── cli_config.py        # CLI setup wizard (run via setup.sh)
└── security/            # CSP, rate limiting, observability
```

## Key assumptions (explicit, for the next operator)

1. **Anthropic API is the primary LLM provider.** Extraction and synthesis require an Anthropic key. OpenRouter is supported as an alternative but not the default.
2. **Local embeddings (fastembed) run in the backend container.** No external embedding service needed unless you configure `EMBED_PROVIDER=openai_compat` or `openrouter`.
3. **File ingestion from MCP is container-relative.** Passing a local file path (e.g., `/home/claw/foo.pdf`) to `ingest_source` may fail because the MCP container can't see that path. Prefer URLs or copy files to a container-accessible location.
4. **`REFERENCES` edges are ingest-time only.** If page B references page A via `[[wikilink]]` but page A doesn't exist yet at ingest time, the edge won't be created. Run `make rebuild-indexes` afterward.
5. **First boot hashes `OWNER_PASSWORD`.** After the first successful login, the plaintext value in `.env` is ignored. To change the password later, update the hash in SQLite directly or wipe and re-create.
6. **Caddy auto-generates self-signed certs when `ARCHIVUM_HOST` is unset.** For prod with a real domain, set `ARCHIVUM_HOST=archivum.example.com` and Caddy will fetch Let's Encrypt certs automatically.
7. **Qdrant collection is created with the dimension detected from `EMBED_MODEL`.** If the model changes and dimension-mismatch recreation is enabled (`QDRANT_RECREATE_COLLECTION_ON_DIM_MISMATCH=true`), existing vectors are cleared on mismatch.

## Further reading (linked docs)

- [Ingest pipeline deep-dive](../architecture/ingest.md)
- [Graph model (Kuzu)](../architecture/graph-model.md)
- [MCP server tool reference](../architecture/mcp.md)
- [Retrieval + context sizing](../architecture/retrieval.md)
- [Claude/LLM notes](../llm/claude.md)
- [Product requirements](../prd/archivum-prd-v1.0.md)
- [Build progress](../project/progress.md)
- [OpenClaw cron management runbook](./openclaw-cron-management-runbook.md)

## "Done" checklist (handoff)
Before handing off:
- Stack starts (`docker compose up -d --build`)
- All 5 services health-check pass (`docker compose ps` shows healthy/up)
- At least one ingest completed successfully (via MCP tool)
- New content is visible in wiki/search
- Graph view shows expected neighbors for that content
- You recorded any special assumptions about file ingestion paths
