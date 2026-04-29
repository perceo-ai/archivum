# Graph Report - archivum  (2026-04-28)

## Corpus Check
- 43 files · ~23,886 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 326 nodes · 618 edges · 17 communities detected
- Extraction: 68% EXTRACTED · 32% INFERRED · 0% AMBIGUOUS · INFERRED: 197 edges (avg confidence: 0.63)
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

## God Nodes (most connected - your core abstractions)
1. `Settings` - 69 edges
2. `CurrentUser` - 22 edges
3. `get_db()` - 22 edges
4. `ingest()` - 19 edges
5. `get_settings()` - 15 edges
6. `ParsedDoc` - 15 edges
7. `Archivum` - 12 edges
8. `_run()` - 11 edges
9. `apiFetch()` - 11 edges
10. `WikiPage` - 10 edges

## Surprising Connections (you probably didn't know these)
- `search_wiki()` --calls--> `search()`  [INFERRED]
  backend/archivum/mcp/server.py → frontend/src/api.ts
- `Settings` --uses--> `JWT creation/validation, password hashing, FastAPI dependencies.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/auth.py
- `Settings` --uses--> `Return bcrypt hash of *plaintext*.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/auth.py
- `Settings` --uses--> `Return True if *plaintext* matches *hashed*.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/auth.py
- `Settings` --uses--> `Return (raw_token, hashed_token) pair.`  [INFERRED]
  backend/archivum/config.py → backend/archivum/auth.py

## Hyperedges (group relationships)
- **Ingest to Knowledge Graph Flow** — archivum_prd_v1_0_ingest_pipeline, archivum_prd_v1_0_wiki_agent, archivum_prd_v1_0_markdown_canonical, archivum_prd_v1_0_qdrant, archivum_prd_v1_0_neo4j [EXTRACTED 1.00]
- **Query Synthesis Pipeline** — archivum_prd_v1_0_query_engine, archivum_prd_v1_0_semantic_search, archivum_prd_v1_0_qdrant, archivum_prd_v1_0_neo4j [EXTRACTED 1.00]
- **Remote Access Security Stack** — archivum_prd_v1_0_tailscale, archivum_prd_v1_0_cloudflare_tunnel, archivum_prd_v1_0_caddy [EXTRACTED 1.00]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.09
Nodes (39): AuthResponse, login(), me(), Authentication routes: /api/auth/*, refresh(), register(), _set_access_cookie(), _set_refresh_cookie() (+31 more)

### Community 1 - "Community 1"
Cohesion: 0.13
Nodes (31): Settings, BaseSettings, ExtractionResult, get_agent(), LLM wiki agent: extract entities, generate wiki pages, build graph structure.  U, Generate a minimal page when the LLM call fails or produces no pages., Convert a title to a kebab-case slug., Extract structured wiki data from a ParsedDoc.          Uses prompt caching on t (+23 more)

### Community 2 - "Community 2"
Cohesion: 0.08
Nodes (24): handleCreatePage(), handleFileDrop(), onDrop(), handleUrlIngest(), updateFileStatus(), handleSaveAsPage(), handleSubmit(), runSearch() (+16 more)

### Community 3 - "Community 3"
Cohesion: 0.12
Nodes (31): LoginRequest, RegisterRequest, ingest_batch_upload(), ingest_file(), ingest_history(), ingest_url(), Ingest routes: /api/ingest/*  Supports file upload, URL ingest, and batch upload, Ingest a URL and stream progress via SSE. (+23 more)

### Community 4 - "Community 4"
Cohesion: 0.12
Nodes (26): get_graph(), graph_neighbors(), rebuild_indexes(), add_entity_relation(), add_mention(), add_reference(), delete_page_node(), get_all_nodes_edges() (+18 more)

### Community 5 - "Community 5"
Cohesion: 0.11
Nodes (27): Archivum, BeautifulSoup, CodeMirror 6 Editor, Docker Compose Stack, Graph View, Ingest Pipeline, Kuzu, Wiki Lint / Health Check (+19 more)

### Community 6 - "Community 6"
Cohesion: 0.11
Nodes (22): _build_prompt(), query(), lint_wiki(), _unique_slug(), get_page(), graph_neighbors(), ingest_source(), lint_wiki() (+14 more)

### Community 7 - "Community 7"
Cohesion: 0.15
Nodes (21): get_settings(), Application configuration via pydantic-settings (reads from .env)., create_app(), lifespan(), _chunk_text(), delete_page(), embed_texts(), get_client() (+13 more)

### Community 8 - "Community 8"
Cohesion: 0.18
Nodes (10): decode_access_token(), get_current_user(), hash_password(), JWT creation/validation, password hashing, FastAPI dependencies., Resolve the current user from:     1. httpOnly cookie `access_token`     2. Auth, Return bcrypt hash of *plaintext*., Return True if *plaintext* matches *hashed*., Decode and validate an access JWT. Raises HTTPException on failure. (+2 more)

### Community 9 - "Community 9"
Cohesion: 0.18
Nodes (5): StatusBar(), Editor(), ProtectedRoutes(), useAppDispatch(), useAppState()

### Community 10 - "Community 10"
Cohesion: 0.24
Nodes (4): makeWikilinkCompletion(), makeWikilinkPlugin(), wikilinkExtension(), WikilinkWidget

### Community 11 - "Community 11"
Cohesion: 0.33
Nodes (2): loadGraph(), renderGraph()

### Community 12 - "Community 12"
Cohesion: 0.4
Nodes (5): Caddy Reverse Proxy, Cloudflare Tunnel, Security Architecture, Share Links, Tailscale

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): Archivum — self-hosted AI-powered knowledge base.

### Community 15 - "Community 15"
Cohesion: 1.0
Nodes (1): Database layer: SQLite, Qdrant, Kuzu.

### Community 16 - "Community 16"
Cohesion: 1.0
Nodes (1): Ingest layer: parsers, LLM agent, orchestration pipeline.

### Community 17 - "Community 17"
Cohesion: 1.0
Nodes (1): MCP server for Archivum (stdio + SSE).

## Knowledge Gaps
- **27 isolated node(s):** `Archivum — self-hosted AI-powered knowledge base.`, `Application configuration via pydantic-settings (reads from .env).`, `Database layer: SQLite, Qdrant, Kuzu.`, `Ingest layer: parsers, LLM agent, orchestration pipeline.`, `File/URL parsers. Each returns a ParsedDoc dataclass.` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 11`** (7 nodes): `fitAll()`, `handleSearch()`, `loadGraph()`, `renderGraph()`, `zoomIn()`, `zoomOut()`, `GraphView.tsx`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (2 nodes): `Archivum — self-hosted AI-powered knowledge base.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 15`** (2 nodes): `__init__.py`, `Database layer: SQLite, Qdrant, Kuzu.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 16`** (2 nodes): `__init__.py`, `Ingest layer: parsers, LLM agent, orchestration pipeline.`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 17`** (2 nodes): `__init__.py`, `MCP server for Archivum (stdio + SSE).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Settings` connect `Community 1` to `Community 0`, `Community 3`, `Community 4`, `Community 6`, `Community 7`, `Community 8`?**
  _High betweenness centrality (0.375) - this node is a cross-community bridge._
- **Why does `search_wiki()` connect `Community 6` to `Community 2`?**
  _High betweenness centrality (0.172) - this node is a cross-community bridge._
- **Why does `search()` connect `Community 2` to `Community 6`?**
  _High betweenness centrality (0.170) - this node is a cross-community bridge._
- **Are the 66 inferred relationships involving `Settings` (e.g. with `TokenPayload` and `CurrentUser`) actually correct?**
  _`Settings` has 66 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `CurrentUser` (e.g. with `Settings` and `LoginRequest`) actually correct?**
  _`CurrentUser` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `ingest()` (e.g. with `get_settings()` and `create_ingest_log()`) actually correct?**
  _`ingest()` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 13 inferred relationships involving `get_settings()` (e.g. with `lifespan()` and `create_app()`) actually correct?**
  _`get_settings()` has 13 INFERRED edges - model-reasoned connections that need verification._

