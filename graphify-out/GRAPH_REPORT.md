# Graph Report - archivum  (2026-04-29)

## Corpus Check
- 58 files · ~39,713 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 518 nodes · 966 edges · 21 communities detected
- Extraction: 56% EXTRACTED · 44% INFERRED · 0% AMBIGUOUS · INFERRED: 428 edges (avg confidence: 0.6)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]

## God Nodes (most connected - your core abstractions)
1. `Settings` - 184 edges
2. `ParsedDoc` - 37 edges
3. `CurrentUser` - 26 edges
4. `ingest()` - 23 edges
5. `get_db()` - 22 edges
6. `WikiPage` - 19 edges
7. `ExtractionResult` - 19 edges
8. `UnsupportedFileTypeError` - 18 edges
9. `get_settings()` - 16 edges
10. `set_trace_id()` - 12 edges

## Surprising Connections (you probably didn't know these)
- `search_wiki()` --calls--> `search()`  [INFERRED]
  backend/archivum/mcp/server.py → frontend/src/api.ts
- `Settings` --uses--> `Return (raw_token, hashed_token) pair.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/auth.py
- `Settings` --uses--> `aiosqlite wrapper — schema init and CRUD for all tables.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/db/sqlite.py
- `Settings` --uses--> `Create the owner account if it doesn't already exist.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/db/sqlite.py
- `Settings` --uses--> `Return (id, created) where created=True means a new row was inserted.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/db/sqlite.py

## Hyperedges (group relationships)
- **Ingest to Knowledge Graph Flow** — archivum_prd_v1_0_ingest_pipeline, archivum_prd_v1_0_wiki_agent, archivum_prd_v1_0_markdown_canonical, archivum_prd_v1_0_qdrant, archivum_prd_v1_0_neo4j [EXTRACTED 1.00]
- **Query Synthesis Pipeline** — archivum_prd_v1_0_query_engine, archivum_prd_v1_0_semantic_search, archivum_prd_v1_0_qdrant, archivum_prd_v1_0_neo4j [EXTRACTED 1.00]
- **Remote Access Security Stack** — archivum_prd_v1_0_tailscale, archivum_prd_v1_0_cloudflare_tunnel, archivum_prd_v1_0_caddy [EXTRACTED 1.00]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.02
Nodes (113): LoginRequest, RegisterRequest, ingest_batch_upload(), ingest_file(), ingest_history(), ingest_url(), Ingest routes: /api/ingest/*  Supports file upload, URL ingest, and batch upload, Ingest a URL and stream progress via SSE. (+105 more)

### Community 1 - "Community 1"
Cohesion: 0.08
Nodes (51): ExtractionResult, get_agent(), LLM wiki agent: extract entities, generate wiki pages, build graph structure.  U, Extract structured wiki data from a ParsedDoc.          Uses prompt caching on t, Extract structured wiki data from a ParsedDoc.          Uses prompt caching on t, Extract structured wiki data from a ParsedDoc.          Uses prompt caching on t, OpenRouter-backed extraction (entities + relationships)., OpenRouter-backed extraction (entities + relationships). (+43 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (52): get_graph(), graph_neighbors(), lint_wiki(), rebuild_indexes(), lifespan(), new_trace_id(), set_trace_id(), add_entity_relation() (+44 more)

### Community 3 - "Community 3"
Cohesion: 0.07
Nodes (29): handleCreatePage(), handleFileDrop(), onDrop(), handleUrlIngest(), updateFileStatus(), handleNav(), handleSaveAsPage(), handleSubmit() (+21 more)

### Community 4 - "Community 4"
Cohesion: 0.09
Nodes (39): AuthResponse, login(), me(), Authentication routes: /api/auth/*, refresh(), register(), _set_access_cookie(), _set_refresh_cookie() (+31 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (31): _build_prompt(), query(), get_settings(), Application configuration via pydantic-settings (reads from .env)., get_trace_id(), _chunk_text(), delete_page(), embed_texts() (+23 more)

### Community 6 - "Community 6"
Cohesion: 0.11
Nodes (27): Archivum, BeautifulSoup, CodeMirror 6 Editor, Docker Compose Stack, Graph View, Ingest Pipeline, Kuzu, Wiki Lint / Health Check (+19 more)

### Community 7 - "Community 7"
Cohesion: 0.11
Nodes (22): _find_env_file(), main(), _mask_secret(), _parse_env_kv(), _prompt_choice(), _prompt_secret(), _prompt_text(), _set_env_var() (+14 more)

### Community 8 - "Community 8"
Cohesion: 0.17
Nodes (14): Lightweight timing span.      Usage:         with span("qdrant.upsert", slug=slu, span(), _derive_base_url(), _is_azure_openai_base_url(), openai_compat_chat_completion(), openai_compat_stream_tokens(), Stream `delta.content` tokens from an OpenAI-compatible SSE stream., Return (base_url, api_key, headers, params) for OpenAI-compatible chat. (+6 more)

### Community 9 - "Community 9"
Cohesion: 0.31
Nodes (14): create_page(), delete_page(), _deserialize_tags(), get_backlinks(), get_page(), list_pages(), PageDetail, PageSummary (+6 more)

### Community 10 - "Community 10"
Cohesion: 0.22
Nodes (5): StatusBar(), ProtectedRoutes(), reducer(), useAppDispatch(), useAppState()

### Community 11 - "Community 11"
Cohesion: 0.24
Nodes (4): makeWikilinkCompletion(), makeWikilinkPlugin(), wikilinkExtension(), WikilinkWidget

### Community 12 - "Community 12"
Cohesion: 0.33
Nodes (3): handleSearch(), loadGraph(), renderGraph()

### Community 14 - "Community 14"
Cohesion: 0.4
Nodes (5): Caddy Reverse Proxy, Cloudflare Tunnel, Security Architecture, Share Links, Tailscale

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Archivum — self-hosted AI-powered knowledge base.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Database layer: SQLite, Qdrant, Kuzu.

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): Ingest layer: parsers, LLM agent, orchestration pipeline.

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): MCP server for Archivum (stdio + SSE).

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (1): LLM provider helpers (Anthropic, OpenRouter, etc.).

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Configure stdlib logging for all Archivum processes.      Environment:       - L

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Convenience helper so we consistently attach structured fields.

## Knowledge Gaps
- **114 isolated node(s):** `Archivum — self-hosted AI-powered knowledge base.`, `Application configuration via pydantic-settings (reads from .env).`, `Lightweight timing span.      Usage:         with span("qdrant.upsert", slug=slu`, `Reserved keys in `logging.LogRecord` that cannot be overridden via `extra=`.`, `Prevent stdlib logging from raising `KeyError` when `extra` includes a reserved` (+109 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 15`** (2 nodes): `Archivum — self-hosted AI-powered knowledge base.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (2 nodes): `__init__.py`, `Database layer: SQLite, Qdrant, Kuzu.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (2 nodes): `__init__.py`, `Ingest layer: parsers, LLM agent, orchestration pipeline.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 18`** (2 nodes): `__init__.py`, `MCP server for Archivum (stdio + SSE).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (2 nodes): `__init__.py`, `LLM provider helpers (Anthropic, OpenRouter, etc.).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Configure stdlib logging for all Archivum processes.      Environment:       - L`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Convenience helper so we consistently attach structured fields.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Community 0` to `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 7`, `Community 8`, `Community 9`?**
  _High betweenness centrality (0.522) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `Community 5` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 7`?**
  _High betweenness centrality (0.127) - this node is a cross-community bridge._
- **Why does `_TraceMiddleware` connect `Community 7` to `Community 0`, `Community 3`?**
  _High betweenness centrality (0.073) - this node is a cross-community bridge._
- **Are the 181 inferred relationships involving `Settings` (e.g. with `TokenPayload` and `CurrentUser`) actually correct?**
  _`Settings` has 181 INFERRED edges - model-reasoned connections that need verification._
- **Are the 34 inferred relationships involving `ParsedDoc` (e.g. with `WikiPage` and `ExtractionResult`) actually correct?**
  _`ParsedDoc` has 34 INFERRED edges - model-reasoned connections that need verification._
- **Are the 23 inferred relationships involving `CurrentUser` (e.g. with `Settings` and `LoginRequest`) actually correct?**
  _`CurrentUser` has 23 INFERRED edges - model-reasoned connections that need verification._
- **Are the 17 inferred relationships involving `ingest()` (e.g. with `get_settings()` and `set_trace_id()`) actually correct?**
  _`ingest()` has 17 INFERRED edges - model-reasoned connections that need verification._