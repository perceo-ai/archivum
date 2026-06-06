# Archivum

**The wiki that writes itself.**

Self-hosted, AI-powered knowledge base that ingests files and URLs, extracts structured notes via LLMs, and surfaces everything through a wiki editor, semantic search, knowledge graph, and an MCP server your AI clients can query directly.

## What it does

- **Self-hosted wiki that organizes itself** — drop in a PDF, paste a URL, or upload audio and Archivum writes the wiki page, links related concepts, and keeps everything searchable
- **Background agent** — maintains wiki pages, vector embeddings, and a knowledge graph without you lifting a finger
- **MCP server built-in** — connect Claude Desktop, Claude Code, Cursor, VS Code, or any MCP-compatible client and let your AI assistant read and write your wiki
- **One command to start** — `docker compose up -d`; no cloud account, no SaaS, no data leaving your machine (unless you use the Anthropic API)

## Quick Start

```bash
git clone https://github.com/pranavkannepalli/archivum.git
cd archivum
cp .env.example .env          # fill in ANTHROPIC_API_KEY, JWT_SECRET, OWNER_PASSWORD, MCP_API_KEY
docker compose up -d --build
# Open http://localhost
```

Or use the interactive wizard:

```bash
make setup
docker compose up -d --build
```

**Endpoints after boot:**

| URL | What |
|---|---|
| `http://localhost` | Web UI |
| `http://localhost:8000` | REST API |
| `http://localhost:8001/sse` | MCP server (SSE) |

**Optional — TLS + public share subdomain:** set `ARCHIVUM_HOST` in `.env` and update the email in `caddy/Caddyfile`. Caddy will serve `https://$ARCHIVUM_HOST` and `https://share.$ARCHIVUM_HOST` automatically.

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
