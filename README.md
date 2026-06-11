# Archivum

**The wiki that writes itself.**

Self-hosted, AI-powered knowledge base that ingests files and URLs, extracts structured notes via LLMs, and surfaces everything through a wiki editor, semantic search, knowledge graph, and an MCP server your AI clients can query directly.

## What it does

- **Self-hosted wiki that organizes itself** — drop in a PDF or paste a URL and Archivum writes the wiki page, links related concepts, and keeps everything searchable
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

This installs/checks Node.js and Docker, downloads Archivum's minimal runtime files into `~/archivum`, launches the `archivum` CLI guided setup, writes `.env`, pulls the published Docker images, and starts the containers.

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
install.sh / install.ps1
uninstall.sh / uninstall.ps1
update.sh
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

The installer uses the `archivum` Node package. The shell and PowerShell files are compatibility shims that call the local CLI in a source checkout or `npx archivum` in a minimal runtime install.

By default the installer uses published images from GitHub Container Registry. Developers can build locally instead:

```bash
./install.sh --build
```

You can also call the package directly:

```bash
npx archivum install
npx archivum install --build
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

### Uninstall

The default uninstaller stops and removes Archivum containers and the Docker network, but preserves local files, images, and data volumes:

macOS / Linux:

```bash
./uninstall.sh
```

Windows PowerShell:

```powershell
.\uninstall.ps1
```

Optional cleanup flags:

```bash
./uninstall.sh --volumes   # also delete wiki data, raw uploads, SQLite, Kuzu, and Qdrant volumes
./uninstall.sh --images    # also remove locally built Compose images
./uninstall.sh --files     # also remove the local Archivum install directory
./uninstall.sh --yes       # skip confirmation prompts
```

Equivalent package command:

```bash
npx archivum uninstall --volumes --yes
```

PowerShell uses the same options as switches, for example:

```powershell
.\uninstall.ps1 -Volumes -Images
```

Use `--dry-run` on macOS/Linux or `-DryRun` on PowerShell to print the actions without changing anything.

### Update

macOS / Linux:

```bash
./update.sh
```

This refreshes the runtime files, pulls the latest published Docker images, and restarts the stack while preserving `.env` and Docker volumes. Developers can rebuild from source instead:

```bash
./update.sh --build
```

Equivalent package command:

```bash
npx archivum update --build
```

**Endpoints after boot:**

| URL | What |
|---|---|
| `http://localhost` | Web UI |
| `http://localhost:8000` | REST API |
| `http://localhost:8001/sse` | MCP server (SSE) |

**Optional — TLS + public share subdomain:** see [Custom Domain & HTTPS](#custom-domain--https) below.

### Local development without building images

You can run the Python services directly with `uv` and only use Docker for Qdrant:

```bash
docker compose up -d qdrant

cd apps/backend
uv sync

WIKI_DIR=.data/wiki \
RAW_DIR=.data/raw \
DB_PATH=.data/archivum.db \
KUZU_PATH=.data/kuzu \
QDRANT_URL=http://localhost:6333 \
uv run uvicorn archivum.main:app --reload --host 0.0.0.0 --port 8000
```

Run the MCP server in a second shell:

```bash
cd apps/backend
WIKI_DIR=.data/wiki \
RAW_DIR=.data/raw \
DB_PATH=.data/archivum.db \
KUZU_PATH=.data/kuzu \
QDRANT_URL=http://localhost:6333 \
MCP_PORT=8001 \
uv run python -m archivum.mcp.server --sse
```

For frontend-only work:

```bash
cd apps/frontend
npm install
npm run dev
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes* | — | API key for Claude (extraction + synthesis). *Required if using Anthropic provider. |
| `JWT_SECRET` | Yes | `changeme-replace-in-production` | Secret used to sign auth tokens. Generate with `openssl rand -hex 32`. |
| `OWNER_PASSWORD` | Yes | `changeme` | Password for the `admin` user on first boot. |
| `OWNER_USERNAME` | No | `admin` | Username for the owner account. |
| `MCP_API_KEY` | Yes | — | Bearer token for MCP server access. Generate with `openssl rand -hex 32`. |
| `ARCHIVUM_HOST` | No | `localhost` | Public hostname. When set, Caddy provisions TLS via Let's Encrypt. |
| `ARCHIVUM_FRONTEND_PORT` | No | `8473` | Local-only host port for direct access to the frontend container. |
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

## Custom Domain & HTTPS

Caddy handles TLS automatically via Let's Encrypt once your domain points at the machine. There are three things you must do before it works.

### 1. Set your hostname and fix the Caddyfile email

In `.env`:

```
ARCHIVUM_HOST=yourdomain.com
```

In `caddy/Caddyfile`, replace the placeholder email with your real address:

```
{
    email you@youremail.com
}
```

> **Why?** Let's Encrypt explicitly blocks `example.com` as a contact address and will reject the certificate request with a 400 error. Caddy may fall back to ZeroSSL, but the safest path is a real email on a real domain.

### 2. Create DNS records

At your DNS provider (wherever your domain is registered), add two **A records** pointing to your machine's public IP:

| Name | Type | Value |
|---|---|---|
| `yourdomain.com` | A | `<your public IP>` |
| `share.yourdomain.com` | A | `<your public IP>` |

The `share` subdomain is required if you want to use share links or the public wiki on its own hostname.

Find your machine's public IP with:

```bash
curl -s https://api.ipify.org
```

DNS changes can take a few minutes to an hour to propagate. You can check with `dig yourdomain.com` or an online DNS lookup tool.

> **Cloudflare users — Proxy vs DNS-only:** If your domain is on Cloudflare, set the A records to **DNS only (grey cloud)**, not Proxied (orange cloud). With Proxy enabled, Cloudflare terminates TLS at the edge and forwards requests to your origin — but Caddy's ACME http-01 challenge also goes through Cloudflare, which requires your machine to be reachable from Cloudflare's servers on port 80. If that's not the case (e.g., you're on a home network without port forwarding), the challenge silently fails and connections time out. DNS-only lets Caddy talk directly to Let's Encrypt without any proxy in the way. If you want to keep the Cloudflare Proxy for CDN/DDoS benefits, use a [Cloudflare Tunnel](#cloudflare-tunnel) instead — it bypasses this entirely.

### 3. Make sure ports 80 and 443 are reachable

Caddy proves domain ownership by answering an HTTP challenge on port 80, then serves HTTPS on 443. Both ports must be reachable from the internet.

- **Cloud VPS / dedicated server:** check that your firewall or security group allows inbound TCP 80 and 443.
- **Home network / NAT router:** add port-forward rules in your router admin panel pointing external ports 80 and 443 to the local IP of the machine running Archivum.
- **Can't open ports at all?** Use a [Cloudflare Tunnel](#cloudflare-tunnel) instead — it punches through NAT without any port forwarding.

### 4. Apply the changes

```bash
docker compose restart caddy
```

Caddy will fetch certificates for `yourdomain.com` and `share.yourdomain.com` on startup and renew them automatically. The share subdomain only serves `/share/*`, `/public*`, `/api/share/*`, and `/api/public/*`; all other paths return 404.

---

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

The repo includes a GitHub Actions workflow at `.github/workflows/docker-publish.yml`. On pushes to `main` or tags like `v1.2.3`, it automatically publishes multi-arch `linux/amd64` and `linux/arm64` images to GitHub Container Registry:

```text
ghcr.io/pranavkannepalli/archivum-backend
ghcr.io/pranavkannepalli/archivum-frontend
ghcr.io/pranavkannepalli/archivum-mcp
```

To trigger a manual publish without a push, run the workflow via GitHub Actions → **Publish Docker Images** → **Run workflow**, and set `publish_images` to `true`. Running it without that flag only runs validation (tests + build) without pushing images.

## Architecture

| Service | Container | Exposes | Role |
|---|---|---|---|
| `backend` | `archivum-backend` | 8000 (internal) | FastAPI — ingestion, search, wiki CRUD, auth |
| `frontend` | `archivum-frontend` | 8080 internal, localhost:8473 default | React + Vite — web UI |
| `mcp` | `archivum-mcp` | 8001 | MCP server (stdio + HTTP/SSE) |
| `qdrant` | `archivum-qdrant` | 6333, 6334 | Vector database for semantic search |
| `caddy` | `archivum-caddy` | 80, 443 | Reverse proxy, TLS termination |

Storage is local-first:

| Store | Default path / volume | Purpose |
|---|---|---|
| Markdown wiki | `wiki_data` mounted at `/data/wiki` | Canonical page content |
| Raw uploads | `raw_data` mounted at `/data/raw` | Original ingested source files |
| SQLite | `db_data` mounted at `/data/archivum.db` | Users, auth state, page metadata, share links, ingest log, keyword FTS |
| Kuzu | `kuzu_data` mounted at `/data/kuzu` | Embedded graph database for page/entity relationships |
| Qdrant | `qdrant_data` mounted in the Qdrant container | Vector index for semantic search |

Markdown files are the canonical source of truth. SQLite stores operational metadata. Qdrant and Kuzu are derived indexes and can be rebuilt from the wiki content.

See [docs/architecture/infra.md](docs/architecture/infra.md) for the full deployment and storage breakdown.

## MCP Client Setup

The MCP server supports both **stdio** (for desktop apps that shell out) and **HTTP/SSE** (for web clients and editors). Both transports expose the same tools.

### Claude Desktop

Add to `~/.claude/claude_desktop_config.json` (or `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "archivum": {
      "command": "docker",
      "args": ["exec", "-i", "archivum-mcp", "python", "-m", "archivum.mcp.server", "--stdio"],
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
cd apps/backend
UV_PYTHON=python3.12 npx @modelcontextprotocol/inspector --cli --method tools/list \
  uv run python -m archivum.mcp.server --stdio
```

For SSE, start the MCP server and run Inspector against `/sse`:

```bash
cd apps/backend
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
| Media — audio | MP3, WAV, M4A, OGG (optional local Whisper transcription) |
| Media — video | MP4, MKV, WebM (optional ffmpeg audio extraction + local Whisper transcription) |
| Email | EML, MBOX |
| Subtitles | SRT, VTT |

## Performance Targets

Audio and video transcription require the optional `audio` Python extra plus `ffmpeg` for video extraction. The default Docker images omit Whisper/Torch/ffmpeg so the backend and MCP images stay small. For local media transcription outside the published images:

```bash
cd apps/backend
uv sync --extra audio
# Also install ffmpeg with your OS package manager if you need video extraction.
```

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

## Graph export (local mock-safe demo)

Use the repo-owned mock graph fixtures (no DB required) and write inspectable artifacts to disk:

```bash
make graph-export-demo
```

This writes:
- `graph-export-out/graph.json`
- `graph-export-out/graph.html` (self-contained visualisation)
- `graph-export-out/manifest.json`

Also, the frontend graph endpoints are mock-safe:
- `GET /api/graph` falls back to the same demo graph if Kuzu DB export fails
- `GET /api/graph/demo` returns the demo graph explicitly

To open the HTML:
- macOS/Linux: `open graph-export-out/graph.html` / `xdg-open graph-export-out/graph.html`
- or just `file://.../graph-export-out/graph.html`

