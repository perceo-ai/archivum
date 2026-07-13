# Infrastructure and Storage

Archivum is a local-first Docker Compose application. The default stack keeps application data on the host through Docker volumes and uses managed external services only when you configure hosted LLM or embedding providers.

## Services

| Service | Runtime | Responsibility |
|---|---|---|
| `backend` | Python + FastAPI | REST API, auth, ingestion, wiki CRUD, search/query endpoints, share/export routes |
| `frontend` | React + Vite served by nginx | Browser wiki UI |
| `mcp` | Python MCP SDK | MCP tools over stdio and HTTP/SSE |
| `qdrant` | `qdrant/qdrant:v1.17.1` | Vector search |
| `ollama` | `ollama/ollama:latest` | Optional local LLM/embedding runtime |
| `caddy` | `caddy:2-alpine` | Reverse proxy, TLS, share/public routing |

Published-image installs combine:

```bash
docker compose -f docker-compose.yml -f docker-compose.images.yml up -d --no-build
```

Source builds use:

```bash
docker compose up -d --build
```

## Local Stores

| Store | Container path | Docker volume | Purpose | Rebuildable |
|---|---|---|---|---|
| Markdown wiki | `/data/wiki` | `wiki_data` | Canonical page files | No |
| Raw sources | `/data/raw` | `raw_data` | Original uploaded files | No |
| SQLite | `/data/archivum.db` | `db_data` | Users, JWT refresh tokens, page metadata, share links, ingest logs, keyword FTS | Partially |
| Kuzu | `/data/kuzu` | `kuzu_data` | Graph pages, entities, and relationships | Yes |
| Qdrant | `/qdrant/storage` | `qdrant_data` | Embedding vectors and payloads | Yes |
| Ollama | `/root/.ollama` | `ollama_data` | Local models | Yes |

Markdown is the canonical knowledge store. SQLite is operational metadata. Qdrant and Kuzu are derived indexes and can be rebuilt from wiki content.

## Network Shape

- Caddy exposes ports `80` and `443`.
- Frontend is also bound to `127.0.0.1:${ARCHIVUM_FRONTEND_PORT:-8473}` for direct local access.
- REST API is routed through Caddy at `/api/*`; the backend listens on port `8000` inside Compose.
- MCP SSE is exposed on host port `8001`.
- Qdrant ports `6333` and `6334` are exposed for local debugging.
- Ollama is exposed on host port `11434`.

## Environment

Important configuration lives in `.env` and is documented in [.env.example](../../.env.example).

Provider choices:

| Concern | Options |
|---|---|
| Extraction LLM | `anthropic`, `openrouter`, `openai_compat`, `ollama` |
| Query synthesis LLM | `anthropic`, `openrouter`, `openai_compat`, `ollama` |
| Embeddings | `local`, `openai_compat`, `openrouter`, `ollama` |

Default embeddings use local fastembed with `BAAI/bge-small-en-v1.5`.

## Optional Heavy Capabilities

The published backend and MCP images omit Whisper, Torch, and ffmpeg. Text, document, web, office, data, code, subtitle, and email parsing are included. Image parsing requires Anthropic vision. Audio/video transcription requires:

```bash
cd apps/backend
uv sync --extra audio
# Install ffmpeg with your OS package manager for video files.
```

## Development

For backend or MCP work, start only Qdrant in Docker:

```bash
docker compose up -d qdrant
```

Backend:

```bash
cd apps/backend
uv sync
WIKI_DIR=.data/wiki RAW_DIR=.data/raw DB_PATH=.data/archivum.db KUZU_PATH=.data/kuzu QDRANT_URL=http://localhost:6333 uv run uvicorn archivum.main:app --reload --port 8000
```

MCP:

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
