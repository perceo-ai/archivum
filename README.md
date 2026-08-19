# Archivum

A self-hosted, Obsidian-style second brain: a private markdown wiki in your browser, backed by files on disk, with a built-in MCP server that hands the same vault to your AI agents.

## About

Archivum keeps your knowledge base as plain markdown files you own, then layers a browser wiki, semantic search, cited Q&A, and file/URL ingest on top. It kills the trade-off between a local vault you control and a hosted app you have to hand your notes to — everything runs on your own machine, and the same content is exposed to Claude Desktop, Claude Code, Cursor, and other MCP clients without a third party in the loop.

Archivum keeps markdown editable for humans while maintaining rebuildable semantic and graph indexes for search, citations, and agent context.

Archivum organizes your notes, projects, sources, and agent context around you as the center of the graph. The default view starts from your owner profile, then lets you zoom into projects, thoughts, people, code, and decisions.

## Part of the Perceo stack

Archivum is part of [Perceo](https://perceo.ai) — a local-first developer suite. Related tools:

- [Archductor](https://github.com/perceo-ai/conductor-arch)
- [Archfleet](https://github.com/perceo-ai/archfleet)

Docs for the whole stack live at [docs.perceo.ai](https://docs.perceo.ai).

## Install

Requirements:

- Docker Engine 24+ with Docker Compose v2
- Node.js 20+
- An Anthropic, OpenRouter, or OpenAI-compatible key — or a local Ollama setup

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

The installer writes `.env`, generates missing secrets, and starts the stack using published images via `docker-compose.images.yml`. To build from local source instead:

```bash
./install.sh --build
```

Manual setup, without the installer:

```bash
cp .env.example .env
# Set OWNER_PASSWORD, JWT_SECRET, MCP_API_KEY, and your LLM provider key.
docker compose -f docker-compose.yml -f docker-compose.images.yml up -d --no-build
```

Required `.env` values: `OWNER_PASSWORD`, `JWT_SECRET` (`openssl rand -hex 32`), and `MCP_API_KEY` (`openssl rand -hex 24`). See [.env.example](.env.example) for the full reference.

## Quickstart

Once the stack is up:

| URL | Purpose |
|---|---|
| `http://localhost` | Web app through Caddy |
| `http://localhost:8473` | Frontend container, direct |
| `http://localhost/api/*` | REST API through Caddy |
| `http://localhost:8001/sse` | MCP HTTP/SSE endpoint |

Log in with `OWNER_USERNAME` (`admin` by default) and your `OWNER_PASSWORD`. From there you can create pages, ingest files and URLs, search, run cited queries, and explore the graph.

Wire up an MCP client. Claude Desktop over stdio:

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

Editors and web clients over HTTP/SSE:

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

MCP tools exposed to agents: `ingest_source`, `search_wiki`, `list_pages`, `get_page`, `write_page`, `query`, `graph_neighbors`, `lint_wiki`, and `dispatch_command` (a text wrapper over the above).

## How it works

1. **Editable markdown is the source of truth.** Markdown pages live in the `wiki_data` volume; original uploads land in `raw_data`. Canonical knowledge rows preserve page-authored content and its provenance, while indexes are derived and rebuildable.
2. **Ingest normalizes sources.** File paths and URLs are parsed into wiki pages with source metadata, then chunked and indexed. Supported inputs include markdown, PDF, HTML, EPUB, DOCX/PPTX/XLSX, CSV/JSON, ZIP archives, source code, RTF/XML, EML/MBOX, subtitles, images, and optional audio/video transcripts.
3. **Canonical knowledge powers the vault.** Canonical knowledge rows preserve the owner profile, page-authored content, projects, thoughts, extracted entities, relationships, citations, confidence, and extraction method. Qdrant (`qdrant_data`), Kuzu (`kuzu_data`), FTS, and code lexical indexes are rebuildable projections.
4. **Search and Q&A run over your content.** Retrieval defaults to `person:self` when the caller does not provide another seed, returns cited context and ranked excerpts, and `query` synthesizes an answer with citations back to the source pages.
5. **Caddy fronts the app.** It terminates TLS and routes the browser UI, REST API, and MCP endpoint. Set `ARCHIVUM_HOST` and point DNS at the host for automatic HTTPS.
6. **Agents reach the same vault over MCP** via stdio or HTTP/SSE — reading, writing, searching, and querying the identical data the browser sees.
7. **Captured sessions become governed memory.** Distillation turns a captured conversation into cited memory atoms, scenario memory, an owner profile, and — when real tool steps were recorded — a reusable skill. Anything below the confidence threshold goes to human review instead of being written silently, and an agent only receives the assets you bound to it. This path is deterministic and makes no LLM call. See [memory assets](docs/architecture/memory-assets.md).

To refresh page vectors, page nodes, and wikilink reference edges in the legacy page-based Qdrant/Kuzu projections, run:

```bash
node packages/archivum-cli/src/index.js wiki rebuild-indexes
```

This command upserts those page records and reference edges. It does not remove stale page vectors or nodes, update entity/mention/relationship projections, or rebuild canonical knowledge projections, FTS, or the code lexical index.

## Features

- ✅ Markdown pages stored on disk as canonical content
- ✅ File and URL ingest with a broad parser matrix and source metadata
- ✅ Semantic search over the vault (Qdrant)
- ✅ Question answering with citations back to source pages
- ✅ Built-in MCP server (stdio + HTTP/SSE) for Claude Desktop, Claude Code, Cursor, and VS Code
- ✅ Graph audit — clusters, shortest paths, surprising connections, and a plain-language provenance report
- ✅ Governed memory assets — typed, versioned, reviewable memory that agents can be equipped with by name
- ✅ Deterministic session distillation — captured conversations become cited memory with no LLM call
- ✅ Docker Compose deployment with SQLite, Qdrant, Kuzu, Ollama, and Caddy
- ✅ Pluggable LLM and embedding providers: Anthropic, OpenRouter, OpenAI-compatible, or local Ollama/fastembed
- 🚧 Browser vault navigation — folder/page APIs and file-tree UI exist; click-through needs release smoke
- 🚧 Wikilinks and backlinks — CodeMirror extension and backlinks API/UI exist; browser smoke pending
- 🚧 Graph exploration — Kuzu graph API and frontend view exist; browser smoke pending
- 🚧 Sharing, public wiki, and HTML/PDF export — code exists (`/share/{token}`, `/public`, `/api/export`); manual release smoke pending
- 🚧 Local media transcription (Whisper/ffmpeg) — installable from Settings, emits timestamped audio/video transcript text when dependencies are installed, and is omitted from published images to keep installs small
- 🚧 Life OS workflows (daily notes, projects, tasks) — MCP tools and routes exist; early surface, not the main positioning

## Operations

```bash
./update.sh                         # back up precious data, pull/update, and restart
./update.sh --no-backup             # update without creating a pre-update backup
node packages/archivum-cli/src/index.js recovery backup
node packages/archivum-cli/src/index.js recovery validate backups/<backup-dir>
node packages/archivum-cli/src/index.js recovery restore backups/<backup-dir> --dry-run
node packages/archivum-cli/src/index.js recovery restore backups/<backup-dir> --yes
./uninstall.sh                      # remove containers/network, keep data
./uninstall.sh --volumes            # also delete wiki/raw/db/Kuzu/Qdrant/Ollama volumes

docker compose logs -f backend
docker compose logs -f mcp
docker compose restart backend
docker compose down
```

## Documentation

- [Documentation index](docs/README.md)
- [Infrastructure and storage](docs/architecture/infra.md)
- [Ingest pipeline](docs/architecture/ingest.md)
- [MCP server tools](docs/architecture/mcp.md)
- [Retrieval and context sizing](docs/architecture/retrieval.md)
- [Graph model and graph audit](docs/architecture/graph-model.md)
- [Memory assets, distillation, and agent loadouts](docs/architecture/memory-assets.md)
- [Agent guide](docs/agent-guide.md)

## License

Apache-2.0. See [LICENSE](LICENSE).
