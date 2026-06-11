# Infrastructure and Storage

Archivum is a local-first Docker Compose app. The published deployment runs five services:

| Service | Image / runtime | Responsibility |
|---|---|---|
| `backend` | Python + FastAPI | REST API, auth, ingestion pipeline, wiki CRUD, search/query endpoints |
| `frontend` | React + Vite served by nginx | Browser UI |
| `mcp` | Python MCP SDK | MCP tools for ingest, search, page reads/writes, graph neighbors, and query synthesis |
| `qdrant` | `qdrant/qdrant` | Vector database for semantic search |
| `caddy` | `caddy:2-alpine` | Reverse proxy, TLS, public/share routing |

## Local Stores

All application data is local by default.

| Store | Container path | Docker volume | What it stores | Rebuildable |
|---|---|---|---|---|
| Wiki markdown | `/data/wiki` | `wiki_data` | Canonical page files | No, this is source data |
| Raw sources | `/data/raw` | `raw_data` | Uploaded source files | No, this is source data |
| SQLite | `/data/archivum.db` | `db_data` | Users, JWT refresh tokens, page metadata, share links, ingest logs, keyword FTS | Partially |
| Kuzu | `/data/kuzu` | `kuzu_data` | Embedded graph database for pages, entities, and relationships | Yes |
| Qdrant | `/qdrant/storage` | `qdrant_data` | Embedding vectors and payloads for semantic search | Yes |

Markdown is the canonical knowledge store. SQLite is the operational metadata store. Qdrant and Kuzu are derived indexes that can be rebuilt from page content when needed.

## Database Choices

Archivum currently uses:

| Concern | Database | Why |
|---|---|---|
| Metadata and auth | SQLite with WAL | Single-file local database, no extra container, enough for a single-user/self-hosted deployment |
| Vector search | Qdrant | Purpose-built vector index with a stable Docker image and async Python client |
| Graph navigation | Kuzu | Embedded graph database, much lighter than running Neo4j for the v1 self-hosted target |

There is no Postgres or hosted database in the default architecture. External network calls happen only for configured LLM or embedding providers, unless both are pointed at local providers such as Ollama.

## Optional Heavy Capabilities

The base backend and MCP images are intended to stay small enough to publish as general-purpose runtime images. Heavy capabilities should be packaged outside the base images.

Current split:

| Capability | Default image | Optional install |
|---|---|---|
| Text, documents, web pages, office files, code, subtitles, email | Included | Not needed |
| Image description/OCR | Included parser path; requires configured vision-capable LLM provider | Not needed |
| Audio transcription | Omitted from default images | `uv sync --extra audio` |
| Video transcription | Omitted from default images | `uv sync --extra audio` plus system `ffmpeg` |

For published deployments, the preferred pattern is:

1. Keep `archivum-backend` and `archivum-mcp` as core images.
2. Run optional media transcription in a derived image or separate worker when the feature is needed.
3. Keep optional dependency groups in `pyproject.toml` so base image builds do not pull Torch, CUDA, or ffmpeg.

A derived media image can be as simple as:

```Dockerfile
FROM ghcr.io/pranavkannepalli/archivum-backend:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
  && rm -rf /var/lib/apt/lists/*
RUN uv sync --no-dev --frozen --no-cache --extra audio
USER app
```

That image is intentionally separate from the base image because Whisper/Torch wheels are large and can pull CUDA-related packages on Linux.

## Local Development

For local backend or MCP development, do not build Docker images unless you are testing packaging. Start only Qdrant in Docker:

```bash
docker compose up -d qdrant
```

Then run Python services from the repo:

```bash
cd apps/backend
uv sync

WIKI_DIR=.data/wiki \
RAW_DIR=.data/raw \
DB_PATH=.data/archivum.db \
KUZU_PATH=.data/kuzu \
QDRANT_URL=http://localhost:6333 \
uv run uvicorn archivum.main:app --reload --port 8000
```

Run MCP separately when needed:

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

Build Docker images only when validating release packaging:

```bash
docker build -t archivum-backend:local ./apps/backend
docker build -f apps/backend/Dockerfile.mcp -t archivum-mcp:local ./apps/backend
```
