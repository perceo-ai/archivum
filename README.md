# Archivum

**The wiki that writes itself.**

Self-hosted, AI-powered knowledge base that ingests files and URLs, extracts structured notes via LLMs, and surfaces everything through a wiki editor, semantic search, knowledge graph, and an MCP server your AI clients can query directly.

## What it does

- **Self-hosted wiki that organizes itself** — drop in a PDF, paste a URL, or upload audio and Archivum writes the wiki page, links related concepts, and keeps everything searchable
- **Background agent** — maintains wiki pages, vector embeddings, and a knowledge graph without you lifting a finger
- **MCP server built-in** — connect Claude Desktop, Claude Code, Cursor, VS Code, or any MCP-compatible client and let your AI assistant read and write your wiki
- **One command to start** — `docker compose up -d`; no cloud account, no SaaS, no data leaving your machine (unless you use the Anthropic API)

## Quick Start

### One-command server install

Linux/macOS server:

```bash
curl -fsSL https://raw.githubusercontent.com/pranavkannepalli/archivum/main/scripts/bootstrap.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/pranavkannepalli/archivum/main/scripts/bootstrap.ps1 | iex
```

This installs/checks Python and Docker, downloads Archivum's minimal runtime files into `~/archivum`, launches the guided setup, writes `.env`, pulls the published Docker images, and starts the containers.

Override the install directory like this:

```bash
curl -fsSL https://raw.githubusercontent.com/pranavkannepalli/archivum/main/scripts/bootstrap.sh | ARCHIVUM_INSTALL_DIR=/srv/archivum bash
```

The one-command installer downloads only the runtime files needed for published images:

```text
.env.example
docker-compose.yml
docker-compose.images.yml
caddy/Caddyfile
scripts/install.py
```

It does not clone the whole repo unless you ask for that:

```bash
curl -fsSL https://raw.githubusercontent.com/pranavkannepalli/archivum/main/scripts/bootstrap.sh | ARCHIVUM_FULL_CLONE=1 bash
```

### Guided install

The easiest path is the guided installer. It configures access, API keys, LLM providers, embeddings, public publishing, Docker startup, and then starts the stack.

macOS / Linux:

```bash
./install.sh
```

Windows PowerShell:

```powershell
.\install.ps1
```

The installer uses only built-in shell/PowerShell plus Python's standard library. If Python or Docker is missing, it prints exact install steps for your OS and can open the Docker docs.

By default the installer uses published images from GitHub Container Registry. Developers can build locally instead:

```bash
./install.sh --build
```

Published image defaults:

| Service | Image |
|---|---|
| backend | `ghcr.io/pranavkannepalli/archivum-backend:latest` |
| frontend | `ghcr.io/pranavkannepalli/archivum-frontend:latest` |
| MCP | `ghcr.io/pranavkannepalli/archivum-mcp:latest` |

### Manual install

```bash
git clone https://github.com/pranavkannepalli/archivum.git
cd archivum
cp .env.example .env          # fill in ANTHROPIC_API_KEY, JWT_SECRET, OWNER_PASSWORD, MCP_API_KEY
docker compose -f docker-compose.yml -f docker-compose.images.yml up -d --no-build
# Open http://localhost
```

Or use the interactive wizard:

```bash
make setup
```

**Endpoints after boot:**

| URL | What |
|---|---|
| `http://localhost` | Web UI |
| `http://localhost:8000` | REST API |
| `http://localhost:8001/sse` | MCP server (SSE) |

**Optional — TLS + public share subdomain:** set `ARCHIVUM_HOST` in `.env` and update the email in `caddy/Caddyfile`. Caddy will serve `https://$ARCHIVUM_HOST` and `https://share.$ARCHIVUM_HOST` automatically. The share subdomain only serves `/share/*`, `/public*`, `/api/share/*`, and `/api/public/*`.

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes* | — | API key for Claude (extraction + synthesis). *Required if using Anthropic provider. |
| `JWT_SECRET` | Yes | `changeme-replace-in-production` | Secret used to sign auth tokens. Generate with `openssl rand -hex 32`. |
| `OWNER_PASSWORD` | Yes | `changeme` | Password for the `admin` user on first boot. |
| `OWNER_USERNAME` | No | `admin` | Username for the owner account. |
| `MCP_API_KEY` | Yes | — | Bearer token for MCP server access. Generate with `openssl rand -hex 32`. |
| `ARCHIVUM_HOST` | No | `localhost` | Public hostname. When set, Caddy provisions TLS via Let's Encrypt. |
| `LLM_MODEL` | No | `claude-haiku-4-5-20251001` | Model for extraction (entity/relationship parsing). |
| `LLM_SYNTHESIS_MODEL` | No | `claude-sonnet-4-6` | Model for query synthesis (answers with citations). |
| `LLM_EXTRACTION_PROVIDER` | No | `anthropic` | LLM provider for extraction. Options: `anthropic`, `openrouter`, `openai_compat`, `ollama`. |
| `LLM_SYNTHESIS_PROVIDER` | No | `anthropic` | LLM provider for synthesis. Same options as above. |
| `OPENROUTER_API_KEY` | No | — | API key for OpenRouter (alternative to Anthropic). |
| `EMBED_PROVIDER` | No | `local` | Embedding provider. Options: `local` (fastembed, no API), `openai_compat`, `openrouter`, `ollama`. |
| `EMBED_MODEL` | No | `BAAI/bge-small-en-v1.5` | Embedding model name. |
| `EMBED_API_KEY` | No | — | API key for embedding provider (if not `local`). |
| `OLLAMA_BASE_URL` | No | `http://localhost:11434` | Ollama endpoint for fully local LLM/embeddings. |
| `OPENAI_COMPAT_API_KEY` | No | — | API key for any OpenAI-compatible endpoint. |
| `OPENAI_COMPAT_BASE_URL` | No | — | Base URL for custom OpenAI-compatible endpoint. |
| `PUBLIC_WIKI_ENABLED` | No | `false` | Exposes read-only public wiki pages at `/public` and `/api/public/pages`. |

## Publishing

Archivum supports three public publishing modes:

| Mode | URL | Notes |
|---|---|---|
| Page share link | `/share/{token}` | Unguessable token URL for one page. Optional expiry and revocation. |
| Query permalink | `/share/{token}` | Frozen question, answer, and citations captured when the link is created. |
| Public wiki | `/public` | Whole-wiki read-only view. Requires `PUBLIC_WIKI_ENABLED=true`. |

### Cloudflare Tunnel

For external sharing without opening inbound firewall ports, run Caddy locally and point a Cloudflare Tunnel at it:

```bash
cloudflared tunnel login
cloudflared tunnel create archivum
cloudflared tunnel route dns archivum share.your-domain.com
cloudflared tunnel run archivum --url http://localhost:80
```

Set `ARCHIVUM_HOST=your-domain.com` so Caddy recognizes both `your-domain.com` and `share.your-domain.com`. For a persistent service, create `~/.cloudflared/config.yml`:

```yaml
tunnel: archivum
credentials-file: /Users/you/.cloudflared/<tunnel-id>.json

ingress:
  - hostname: share.your-domain.com
    service: http://localhost:80
  - hostname: your-domain.com
    service: http://localhost:80
  - service: http_status:404
```

Then run `cloudflared service install` on the host. Keep `PUBLIC_WIKI_ENABLED=false` if you only want token-gated share links.

## Publishing Docker Images

The repo includes a GitHub Actions workflow at `.github/workflows/docker-publish.yml`. On pushes to `main`, tags like `v1.2.3`, or manual workflow dispatch, it publishes multi-arch `linux/amd64` and `linux/arm64` images to GitHub Container Registry:

```text
ghcr.io/pranavkannepalli/archivum-backend
ghcr.io/pranavkannepalli/archivum-frontend
ghcr.io/pranavkannepalli/archivum-mcp
```

VS Code tasks are also included:

| Task | What |
|---|---|
| `Archivum: compose up with published images` | Starts using GHCR images, no local build. |
| `Archivum: build local images` | Builds local Docker images for development. |
| `Archivum: publish backend image` | Buildx-pushes backend image. |
| `Archivum: publish MCP image` | Buildx-pushes MCP image. |
| `Archivum: publish frontend image` | Buildx-pushes frontend image. |

## Architecture

| Service | Container | Exposes | Role |
|---|---|---|---|
| `backend` | `archivum-backend` | 8000 (internal) | FastAPI — ingestion, search, wiki CRUD, auth |
| `frontend` | `archivum-frontend` | 3000 (internal) | React + Vite — web UI |
| `mcp` | `archivum-mcp` | 8001 | MCP server (stdio + HTTP/SSE) |
| `qdrant` | `archivum-qdrant` | 6333, 6334 | Vector database for semantic search |
| `caddy` | `archivum-caddy` | 80, 443 | Reverse proxy, TLS termination |

Data is persisted in Docker named volumes (`wiki_data`, `raw_data`, `db_data`, `kuzu_data`, `qdrant_data`). Markdown files in `wiki_data` are the canonical source of truth — Qdrant and the Kuzu graph are derived indexes that can be rebuilt.

## MCP Client Setup

The MCP server supports both **stdio** (for desktop apps that shell out) and **HTTP/SSE** (for web clients and editors). Both transports expose the same tools.

### Claude Desktop

Add to `~/.claude/claude_desktop_config.json` (or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "archivum": {
      "command": "docker",
      "args": ["exec", "-i", "archivum-mcp", "python", "-m", "archivum.mcp"],
      "env": { "MCP_API_KEY": "your-mcp-api-key" }
    }
  }
}
```

### Claude Code

```bash
/mcp add
```

Then provide the same `command`/`args`/`env` values as above, or paste the JSON block when prompted.

### Cursor / Windsurf / VS Code

Add to your editor's MCP settings (e.g., `.cursor/mcp.json` or VS Code `settings.json`):

```json
{
  "mcpServers": {
    "archivum": {
      "url": "http://localhost:8001/sse",
      "headers": { "Authorization": "Bearer your-mcp-api-key" }
    }
  }
}
```

### ChatGPT and other web clients

Use the HTTP/SSE endpoint directly:

```
http://localhost:8001/sse
Authorization: Bearer your-mcp-api-key
```

### MCP Inspector validation

Validate tool schemas locally with:

```bash
cd backend
UV_PYTHON=python3.12 npx @modelcontextprotocol/inspector --cli --method tools/list \
  uv run python -m archivum.mcp.server --stdio
```

For SSE, start the MCP server and run Inspector against `/sse`:

```bash
cd backend
UV_PYTHON=python3.12 uv run python -m archivum.mcp.server --sse
npx @modelcontextprotocol/inspector --cli --method tools/list http://127.0.0.1:8001/sse
```

### Available MCP Tools

| Tool | What it does |
|---|---|
| `ingest_source` | Ingest a file path or URL and create/update a wiki page |
| `search_wiki` | Semantic search across all wiki content |
| `get_page` | Fetch a single wiki page by slug |
| `list_pages` | List all wiki pages (with optional filters) |
| `write_page` | Create or overwrite a wiki page |
| `query` | Ask a question and get an answer with citations |
| `graph_neighbors` | Return concepts linked to a given node in the knowledge graph |
| `lint_wiki` | Check wiki pages for broken links and missing metadata |

## Supported File Types

| Category | Formats |
|---|---|
| Documents | Markdown, PDF, HTML, EPUB |
| Office | DOCX, XLSX, PPTX, ODT |
| Data | CSV, JSON, YAML |
| Code | Most languages (syntax-aware chunking) |
| Web | URLs (fetched + extracted) |
| Media — images | JPEG, PNG, WebP, GIF (vision extraction) |
| Media — audio | MP3, WAV, M4A, OGG (transcription) |
| Media — video | MP4, MKV, WebM (audio track extracted) |
| Email | EML, MBOX |
| Subtitles | SRT, VTT |

## Performance Targets

| Operation | Target |
|---|---|
| Ingest a 2,000–5,000 word article | < 60 s |
| Query first-token latency | < 3 s |
| Semantic search | < 1 s |

## Data & Privacy

- All wiki data, embeddings, and the knowledge graph are stored locally in Docker volumes on your machine.
- LLM API calls are sent to Anthropic (or your configured provider). To keep everything fully local, set `LLM_EXTRACTION_PROVIDER=ollama`, `LLM_SYNTHESIS_PROVIDER=ollama`, and `EMBED_PROVIDER=ollama`.
- Markdown files are the canonical store — Qdrant and Kuzu are derived indexes. If either gets corrupted or out of sync, rebuild with:

```bash
curl -s -X POST http://localhost:8000/api/rebuild-indexes \
  -H "Authorization: Bearer $(grep MCP_API_KEY .env | cut -d= -f2)"
```

## Common Operations

View logs:

```bash
docker compose logs -f backend
docker compose logs -f mcp
```

Restart a single service:

```bash
docker compose restart backend
```

Stop everything (data is preserved in volumes):

```bash
docker compose down
```

Wipe all data and start fresh:

```bash
docker compose down -v
```
