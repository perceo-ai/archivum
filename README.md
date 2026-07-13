# Archivum

**A self-hosted, server-hosted Obsidian-style second brain.**

Archivum runs a private markdown wiki in your browser, stores notes as local files, and exposes the same knowledge base to AI agents through MCP. It is built for people who want Obsidian-style vault navigation, backlinks, wikilinks, file and URL ingest, semantic search, graph exploration, sharing, export, and agent access without handing their whole knowledge base to a hosted app.

## What You Get

- Markdown pages stored on disk as the canonical source of truth
- Browser wiki with folders, backlinks, `[[wikilinks]]`, autosave, search, graph, and ingest workflows
- File and URL ingest that turns sources into searchable wiki pages with source metadata
- Keyword/semantic search and question answering with citations from your wiki
- Share links, optional read-only public wiki pages, and HTML/PDF page export
- Built-in MCP server for Claude Desktop, Claude Code, Cursor, VS Code, and other MCP clients
- Docker Compose deployment with local SQLite, Qdrant, Kuzu, Ollama, and Caddy

## Quick Start

Requirements:

- Docker Engine 24+ with Docker Compose v2
- Node.js 20+
- An Anthropic API key, OpenRouter key, OpenAI-compatible endpoint, or local Ollama setup

```bash
git clone https://github.com/pranavkannepalli/archivum.git
cd archivum
./install.sh
```

Windows PowerShell:

```powershell
git clone https://github.com/pranavkannepalli/archivum.git
cd archivum
.\install.ps1
```

The installer writes `.env`, generates missing secrets, and starts the Docker Compose stack. By default it uses published images through `docker-compose.images.yml`.

For a local source build:

```bash
./install.sh --build
```

Manual setup:

```bash
cp .env.example .env
# Fill in OWNER_PASSWORD, JWT_SECRET, MCP_API_KEY, and your selected LLM provider key.
docker compose -f docker-compose.yml -f docker-compose.images.yml up -d --no-build
```

After boot:

| URL | Purpose |
|---|---|
| `http://localhost` | Web app through Caddy |
| `http://localhost:8473` | Direct frontend container port |
| `http://localhost/api/*` | REST API through Caddy |
| `http://localhost:8001/sse` | MCP HTTP/SSE endpoint |

Log in with `OWNER_USERNAME` from `.env` (`admin` by default) and the `OWNER_PASSWORD` you configured.

## Configuration

Important `.env` values:

| Variable | Required | Notes |
|---|---|---|
| `OWNER_USERNAME` | No | Login username. Defaults to `admin`. |
| `OWNER_PASSWORD` | Yes | First-boot owner password. It is hashed on startup. |
| `JWT_SECRET` | Yes | Generate with `openssl rand -hex 32`. |
| `MCP_API_KEY` | Yes | Bearer token for MCP clients. Generate with `openssl rand -hex 24`. |
| `LLM_EXTRACTION_PROVIDER` | No | `anthropic`, `openrouter`, `openai_compat`, or `ollama`. |
| `LLM_SYNTHESIS_PROVIDER` | No | Same options as extraction. |
| `ANTHROPIC_API_KEY` | Provider-specific | Required when using Anthropic. |
| `OPENROUTER_API_KEY` | Provider-specific | Required when using OpenRouter. |
| `OPENAI_COMPAT_API_KEY` | Provider-specific | Required when using OpenAI-compatible providers. |
| `EMBED_PROVIDER` | No | `local`, `openai_compat`, `openrouter`, or `ollama`. Defaults to local fastembed. |
| `ARCHIVUM_HOST` | No | Public hostname for Caddy TLS. Leave unset for local use. |
| `PUBLIC_WIKI_ENABLED` | No | Set `true` to expose read-only `/public` wiki pages. Share links work separately. |

See [.env.example](.env.example) for the full reference.

## Ingest

Archivum can ingest URLs and supported files through the web UI, REST API, or MCP.

Backend parser support includes:

| Category | Formats |
|---|---|
| Text | Markdown, TXT, RST |
| Documents | PDF, HTML, EPUB |
| Office | DOCX, PPTX, XLSX/XLS |
| Data | CSV, JSON, JSONL |
| Code/config | Python, JavaScript, TypeScript, Go, Rust, shell, SQL, YAML, TOML, INI, and related source files |
| Communication | EML, MBOX |
| Subtitles | SRT, VTT |
| Images | PNG, JPG/JPEG, WebP, GIF through Anthropic vision |
| Audio/video | MP3, M4A, WAV, OGG, FLAC, MP4, MOV, AVI, MKV, WebM with optional Whisper and ffmpeg support |

Default published images omit Whisper, Torch, and ffmpeg to keep installs smaller. For local media transcription:

```bash
cd apps/backend
uv sync --extra audio
# Install ffmpeg with your OS package manager for video files.
```

## MCP Client Setup

Archivum exposes both stdio and HTTP/SSE MCP transports.

Claude Desktop stdio example:

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

HTTP/SSE example for editors and web clients:

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

Core MCP tools:

| Tool | Purpose |
|---|---|
| `ingest_source` | Ingest a file path or URL into the wiki |
| `search_wiki` | Semantic search over wiki pages |
| `list_pages` / `get_page` | Read wiki pages |
| `write_page` | Create or update a wiki page and re-index it |
| `query` | Ask a question and receive an answer with citations |
| `graph_neighbors` | Read one-hop Kuzu graph neighbors |
| `lint_wiki` | Report broken wikilinks, orphan pages, and contradictory claims |
| `dispatch_command` | Text command wrapper for common MCP actions |

Additional Life OS tools exist for daily notes, projects, and tasks. They are early product surfaces and are not the main public positioning for Archivum.

## Sharing, Publishing, and Export

Archivum supports:

- Tokenized read-only page share links at `/share/{token}`
- Tokenized query result share links with frozen answer and citations
- Optional public read-only wiki at `/public` when `PUBLIC_WIKI_ENABLED=true`
- Authenticated page export as HTML or PDF through `/api/export`

For public HTTPS, set `ARCHIVUM_HOST` and point DNS at the host running Caddy. Caddy handles TLS automatically when ports 80 and 443 are reachable.

## Data and Privacy

Archivum keeps your knowledge base local by default:

| Store | Purpose |
|---|---|
| Markdown files in `wiki_data` | Canonical page content |
| Raw files in `raw_data` | Original uploaded sources |
| SQLite in `db_data` | Auth, metadata, ingest log, shares, and keyword search |
| Qdrant in `qdrant_data` | Semantic vectors |
| Kuzu in `kuzu_data` | Graph nodes and edges |

Qdrant and Kuzu are derived indexes. If they get out of sync, rebuild them:

```bash
node packages/archivum-cli/src/index.js wiki rebuild-indexes
```

LLM calls go to the providers you configure. To avoid hosted model calls, configure Ollama for LLMs and embeddings.

## Operations

```bash
./update.sh                 # pull/update and restart
./uninstall.sh              # remove containers/network, keep data
./uninstall.sh --volumes    # also delete wiki/raw/db/Kuzu/Qdrant/Ollama volumes
./uninstall.sh --images     # also remove local Compose images
./uninstall.sh --files      # also remove the local install directory
```

Common Docker commands:

```bash
docker compose logs -f backend
docker compose logs -f mcp
docker compose restart backend
docker compose down
```

## Development

Run frontend tests/build:

```bash
npm test --workspace apps/frontend
npm run build --workspace apps/frontend
```

Run CLI tests:

```bash
npm test --workspace packages/archivum-cli
```

Run backend tests:

```bash
cd apps/backend
uv run --group dev pytest ../../tests -q
```

Run services locally without building application images:

```bash
docker compose up -d qdrant

cd apps/backend
uv sync
WIKI_DIR=.data/wiki RAW_DIR=.data/raw DB_PATH=.data/archivum.db KUZU_PATH=.data/kuzu QDRANT_URL=http://localhost:6333 uv run uvicorn archivum.main:app --reload --port 8000
```

In another shell:

```bash
cd apps/backend
WIKI_DIR=.data/wiki RAW_DIR=.data/raw DB_PATH=.data/archivum.db KUZU_PATH=.data/kuzu QDRANT_URL=http://localhost:6333 MCP_PORT=8001 uv run python -m archivum.mcp.server --sse
```

Frontend:

```bash
cd apps/frontend
npm install
npm run dev
```

## Documentation

- [Documentation index](docs/README.md)
- [Infrastructure and storage](docs/architecture/infra.md)
- [Ingest pipeline](docs/architecture/ingest.md)
- [MCP server tools](docs/architecture/mcp.md)
- [Retrieval and context sizing](docs/architecture/retrieval.md)
- [Graph model](docs/architecture/graph-model.md)
- [Project progress](docs/project/progress.md)
- [Agent guide](docs/agent-guide.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
