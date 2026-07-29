# PER-319: Cited Retrieval, Ask & Agent Context Interfaces — Implementation Plan

**For agentic workers:** Execute tasks in order. Each task is TDD: write a real
pytest test, run it and watch it FAIL, write the minimal real implementation, run
it and watch it PASS, then commit. No placeholders — every step ships real code
with all types defined. Steps are sized 2–5 minutes. Tests live at repo-root
`tests/` (async via `pytest.ini` `asyncio_mode = auto`; MCP tests under
`tests/mcp_tests/`). Run tests from `apps/backend` with
`uv run pytest ../../tests/<file> -q` (or `cd apps/backend && uv run pytest`).

---

## Goal

Build **hybrid cited retrieval** over the derived L2 indexes (SQLite FTS + Qdrant
vectors + Kuzu graph) fused with temporal filters, and assemble **scoped context
packages** (spec §8): seed 2–3 entry nodes → bounded BFS neighborhood → ~5–10
nodes with edges, each annotated with source citation, `extraction_method`, and
`confidence`. Expose cited **Ask** answers, graph exploration, context packages,
and read/write interfaces through the **REST API** and the **MCP server**. Enforce
the critical trust invariant (spec §6.5): answers must surface **"insufficient
evidence"** rather than fabricate certainty. Scope/access labels (spec §4) are
enforced at query time.

## Architecture

Retrieval reads only L2 (droppable/rebuildable) and L1 (citations). It never
mutates L0/L1 except through the existing write-back queue. Flow:

```
query + scope
   │
   ▼
route(source_type)                     # code → graph+lexical ; NL → vector+graph
   │
   ├─ FTS (sqlite)  ─┐
   ├─ Qdrant (NL)   ─┼─► fuse + rank (RRF) ─► seed nodes (2–3)
   └─ Kuzu (graph)  ─┘                              │
                                                    ▼
                                    BFS neighborhood (depth ≤ N, relation-filtered)
                                                    │
                                                    ▼
                              ContextPackage (nodes + edges + citations + method + confidence)
                                                    │
                    ┌───────────────────────────────┼───────────────────────────┐
                    ▼                               ▼                             ▼
                REST /api/retrieve            /api/ask (SSE)               MCP tools
              /api/context-package        (cite | insufficient)      (search, ask, …)
```

Access enforcement wraps every retriever: results carry a `scope`; the query
carries an allowed scope-set derived from `CurrentUser`; out-of-scope nodes are
dropped before fusion.

## Tech Stack

- **Python 3.12**, FastAPI, `pydantic` v2 models, `sse-starlette` `EventSourceResponse`.
- **SQLite/FTS5** (`archivum.db.sqlite`), **Qdrant** (`archivum.db.qdrant_client`),
  **Kuzu** (`archivum.db.graph`) — all async wrappers already exist.
- **MCP** via `mcp.server.fastmcp.FastMCP` (`archivum.mcp.server`).
- **LLM synthesis** via existing providers: `anthropic`, `openrouter_client`,
  `openai_compat_client`, selected by `settings.llm_synthesis_provider`.
- **pytest** + `pytest-asyncio` (auto mode) + `pytest-mock`; fixtures in
  `tests/conftest.py` (`mock_kuzu_conn`, `mock_qdrant_client`, `mock_sqlite_db`,
  `app_client`).

## Global Constraints

1. **Answers cite evidence or declare insufficient.** Every synthesized answer
   either carries ≥1 citation resolving to a `Source`+span, or returns the
   explicit `insufficient_evidence` result. Never fabricate certainty (spec §6.5).
2. **Code uses graph+lexical, not vectors.** Source-type routing: `code`/`structured`
   → Kuzu graph + FTS lexical only; natural-language → Qdrant vector + graph
   (spec §5, §7). Vectors are never queried for code seeds.
3. **Context packages are the primary agent output.** The agent reads the scoped
   subgraph (nodes+edges+citations+method+confidence), not raw documents. Full
   evidence is fetched only when confidence labels demand it (spec §8).
4. **Evolve in place.** Extend existing modules (`db/`, `api/`, `mcp/server.py`),
   reuse existing async wrappers and LLM clients. No new services, no rewrites.
   Retrieval reads L2/L1 only; any index can be dropped and rebuilt (spec §6.6).

---

## File Structure

New and modified files (all under `apps/backend/`):

```
archivum/
  retrieval/
    __init__.py                 # NEW — package
    models.py                   # NEW — Task 1: ContextNode/Edge/Citation/ContextPackage/AskResult + enums
    scope.py                    # NEW — Task 2: allowed_scopes(user), scope_allows()
    fts.py                      # NEW — Task 3: fts_search() → RetrievalHit list
    vector.py                   # NEW — Task 4: vector_search() (NL only) → RetrievalHit list
    graph_seed.py               # NEW — Task 5: graph_seed_search() → RetrievalHit list
    fusion.py                   # NEW — Task 6: reciprocal-rank fusion + ranking
    router.py                   # NEW — Task 7: route(source_type) → retriever set
    bfs.py                      # NEW — Task 8: build_neighborhood() depth-limited, relation-filtered
    citations.py                # NEW — Task 9: resolve_citations() hit → Citation(Source+span)
    package.py                  # NEW — Task 10: build_context_package() end-to-end assembler
    retriever.py                # NEW — Task 11: hybrid_retrieve() orchestrator (route→fuse→rank)
    ask.py                      # NEW — Task 12: assemble_ask() + synthesize() + insufficiency gate
  db/
    graph.py                    # MODIFY — Task 5/8: bfs_neighbors(), typed-node lookups
    sqlite.py                   # MODIFY — Task 9: get_source_span() / provenance lookup helpers
  api/
    retrieval.py                # NEW — Task 13: POST /api/retrieve, POST /api/context-package
    ask.py                      # NEW — Task 14: POST /api/ask (SSE, cited or insufficient)
    graph.py                    # MODIFY — Task 15: GET /api/graph/neighbors (depth param)
  main.py                       # MODIFY — Task 16: include retrieval + ask routers
  mcp/
    server.py                   # MODIFY — Tasks 17–20: search, get_context_package, ask,
                                #          graph_neighbors(depth), write_back tools
tests/
  test_retrieval_models.py      # Task 1
  test_retrieval_scope.py       # Task 2
  test_retrieval_fts.py         # Task 3
  test_retrieval_vector.py      # Task 4
  test_retrieval_graph_seed.py  # Task 5
  test_retrieval_fusion.py      # Task 6
  test_retrieval_router.py      # Task 7
  test_retrieval_bfs.py         # Task 8
  test_retrieval_citations.py   # Task 9
  test_retrieval_package.py     # Task 10
  test_retrieval_retriever.py   # Task 11
  test_retrieval_ask.py         # Task 12
  test_api_retrieval.py         # Task 13
  test_api_ask.py               # Task 14
  test_api_graph_neighbors.py   # Task 15
  test_app_retrieval_wiring.py  # Task 16
  mcp_tests/test_retrieval_tools.py   # Tasks 17–20
```

## Upstream Dependencies

- **PER-317 (graph construction)** — *plan file absent at authoring time.*
  **Assumption:** L1 (SQLite) holds knowledge objects with provenance
  (`chunk_id` + span), `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`,
  `confidence`, `scope`, and temporal validity; Kuzu holds derived typed nodes/edges;
  Qdrant holds NL chunk vectors; FTS5 (`pages_fts`) indexes text. **Bridge:** we
  build on the *current* schema (`pages`, `pages_fts`, Kuzu `Page`/`Entity`) and add
  thin, forward-compatible helpers (`get_source_span`, typed node lookups) that
  degrade gracefully when L1 provenance columns are missing — a node with no
  resolvable span yields a `Citation` with `span=None` and lower confidence, never a
  crash. Where the L1 provenance table is unavailable, citations fall back to
  page-slug granularity (Source = page, span = None).
- **PER-318 (Archgraph code retrieval)** — *plan file absent at authoring time.*
  **Assumption:** a `code_retrieve(seed, scope)` returning a scoped code subgraph
  will exist. **Bridge:** `router.py` defines a `CODE_SEARCH` slot; until PER-318
  lands, code routing uses `graph_seed_search` + `fts_search` (graph+lexical, no
  vectors) directly over Kuzu/FTS. When PER-318 ships, swap the code slot to call
  `code_retrieve` without changing the fusion contract.
- **Existing:** `archivum.db.{sqlite,qdrant_client,graph}`, `archivum.auth`
  (`CurrentUser`, `get_current_user`), `archivum.llm.*`, `archivum.config.Settings`.

**Downstream (PER-320 product UX) consumes** (stabilize these shapes):
- `POST /api/retrieve` → `{ "hits": RetrievalHit[] }` (JSON `RetrievalHit` shape).
- `POST /api/context-package` → `ContextPackage` (nodes/edges/citations/method/confidence).
- `POST /api/ask` → SSE stream: `citations` event → `token`* events →
  `insufficient` event (when weak) → `[DONE]`.
- `GET /api/graph/neighbors?node_id=&depth=` → `{ center, nodes, edges }`.

---

### Task 1 — ContextPackage data model

**Files:** `archivum/retrieval/__init__.py` (new, empty), `archivum/retrieval/models.py` (new),
`tests/test_retrieval_models.py` (new).

**Interfaces:**
- Produces (pydantic v2 `BaseModel`s + `str` `Enum`s):
  ```python
  class ExtractionMethod(str, Enum):
      EXTRACTED = "EXTRACTED"
      INFERRED = "INFERRED"
      AMBIGUOUS = "AMBIGUOUS"

  class SourceType(str, Enum):
      CODE = "code"
      STRUCTURED = "structured"
      NATURAL_LANGUAGE = "natural_language"

  class Citation(BaseModel):
      source_id: str
      source_type: SourceType
      title: str
      origin_uri: str | None = None
      chunk_id: str | None = None
      span: tuple[int, int] | None = None      # char/line offsets, None if unresolved
      excerpt: str | None = None

  class ContextNode(BaseModel):
      id: str
      label: str
      node_type: str                            # "page" | "entity" | "symbol" | ...
      scope: str = "personal"
      extraction_method: ExtractionMethod = ExtractionMethod.EXTRACTED
      confidence: float = 1.0                   # 0.0–1.0
      citations: list[Citation] = []

  class ContextEdge(BaseModel):
      from_id: str
      to_id: str
      relation: str                             # "references" | "mentions" | "calls" | ...
      extraction_method: ExtractionMethod = ExtractionMethod.EXTRACTED
      confidence: float = 1.0

  class ContextPackage(BaseModel):
      query: str
      seeds: list[str]                          # node ids used as BFS roots
      nodes: list[ContextNode]
      edges: list[ContextEdge]
      truncated: bool = False                   # True if neighborhood hit node cap
      insufficient_evidence: bool = False

  class RetrievalHit(BaseModel):
      node_id: str
      label: str
      node_type: str
      scope: str = "personal"
      score: float
      source: str                               # "fts" | "vector" | "graph"
      excerpt: str | None = None

  class AskResult(BaseModel):
      answer: str | None
      citations: list[Citation]
      insufficient_evidence: bool = False
      context_package: ContextPackage | None = None
  ```
- Consumes: nothing.

**Steps:**
- [ ] Write `tests/test_retrieval_models.py::test_context_package_roundtrips`: build a
  `ContextPackage` with one `ContextNode` (one `Citation`, `span=(0,10)`) and one
  `ContextEdge`; assert `.model_dump()["nodes"][0]["extraction_method"] == "EXTRACTED"`
  and `["nodes"][0]["citations"][0]["span"] == [0, 10]`.
- [ ] Run FAIL (`ModuleNotFoundError: archivum.retrieval.models`).
- [ ] Create empty `archivum/retrieval/__init__.py`.
- [ ] Implement `archivum/retrieval/models.py` with the enums and models above.
- [ ] Run PASS.
- [ ] Add `test_askresult_defaults_insufficient_false` and
  `test_extraction_method_rejects_bad_value` (assert `pydantic.ValidationError`
  when `extraction_method="GUESS"`). Run PASS.
- [ ] Commit: `feat(retrieval): add ContextPackage data model`.

---

### Task 2 — Scope / access enforcement helpers

**Files:** `archivum/retrieval/scope.py` (new), `tests/test_retrieval_scope.py` (new).

**Interfaces:**
- Consumes: `archivum.auth.CurrentUser`.
- Produces:
  ```python
  def allowed_scopes(user: CurrentUser) -> set[str]:
      """owner → {"*"} (all); others → {"personal", f"user:{user.username}"}."""
  def scope_allows(allowed: set[str], node_scope: str) -> bool:
      """True if "*" in allowed or node_scope in allowed."""
  def filter_scoped(allowed: set[str], scopes: list[str]) -> list[bool]:
      """Elementwise mask for a list of node scopes."""
  ```

**Steps:**
- [ ] Write `test_owner_sees_all`: `allowed_scopes(CurrentUser(username="me", role="owner", wiki_id="default"))`
  contains `"*"`; `scope_allows(that, "work")` is True.
- [ ] Write `test_non_owner_restricted`: role `"collaborator"` → `scope_allows(scopes, "work")` False,
  `scope_allows(scopes, "personal")` True.
- [ ] Run FAIL. Implement `scope.py`. Run PASS.
- [ ] Add `test_filter_scoped_mask` asserting `[True, False]` for `["personal", "secret"]`
  with a non-owner. Run PASS.
- [ ] Commit: `feat(retrieval): add query-time scope enforcement`.

---

### Task 3 — FTS (keyword) retriever

**Files:** `archivum/retrieval/fts.py` (new), `tests/test_retrieval_fts.py` (new).

**Interfaces:**
- Consumes: `archivum.db.sqlite.search_pages_fts(query, wiki_id, limit)`
  (returns rows: `slug, title, tags, excerpt, rank`).
- Produces:
  ```python
  async def fts_search(
      query: str, *, wiki_id: str = "default", limit: int = 10,
      allowed: set[str] | None = None,
  ) -> list[RetrievalHit]:
      """Keyword hits as RetrievalHit(source="fts", node_type="page",
      score = normalized -rank). Drops rows whose scope is disallowed."""
  ```

**Steps:**
- [ ] Write `test_fts_maps_rows_to_hits`: patch `sqlite.search_pages_fts` (AsyncMock)
  to return two rows with `rank` `-2.0` and `-1.0`; assert two `RetrievalHit`s,
  `source == "fts"`, ordering by descending score (rank `-2.0` ranks better in FTS5).
- [ ] Run FAIL. Implement `fts.py` (normalize score as `1/(1+abs(rank))`; scope
  defaults to `"personal"` when row lacks scope; apply `scope_allows` when `allowed`
  given). Run PASS.
- [ ] Add `test_fts_scope_filtered`: mark one row scope `"work"`, pass
  `allowed={"personal"}`; assert it is dropped. Run PASS.
- [ ] Commit: `feat(retrieval): add FTS keyword retriever`.

---

### Task 4 — Vector retriever (natural-language only)

**Files:** `archivum/retrieval/vector.py` (new), `tests/test_retrieval_vector.py` (new).

**Interfaces:**
- Consumes: `archivum.db.qdrant_client.search_raw(query, wiki_id, limit, settings)`
  (returns `{slug, title, excerpt, score, chunk_index}`).
- Produces:
  ```python
  async def vector_search(
      query: str, *, wiki_id: str = "default", limit: int = 10,
      settings: Settings | None = None, allowed: set[str] | None = None,
  ) -> list[RetrievalHit]:
      """Semantic hits as RetrievalHit(source="vector", node_type="page").
      NL-only: caller (router) must NOT invoke this for code seeds."""
  ```

**Steps:**
- [ ] Write `test_vector_maps_hits`: patch `qdrant.search_raw` (AsyncMock) to return
  two dicts (scores `0.9`, `0.7`); assert two `RetrievalHit`s, `source == "vector"`,
  `node_id == slug`, preserved score order.
- [ ] Run FAIL. Implement `vector.py` (scope default `"personal"`, apply
  `scope_allows`). Run PASS.
- [ ] Add `test_vector_empty_query_returns_empty` (guard blank query → `[]` without
  calling qdrant; assert mock not awaited). Run PASS.
- [ ] Commit: `feat(retrieval): add vector retriever for NL sources`.

---

### Task 5 — Graph seed retriever + Kuzu typed lookup

**Files:** `archivum/retrieval/graph_seed.py` (new), `archivum/db/graph.py` (modify),
`tests/test_retrieval_graph_seed.py` (new).

**Interfaces:**
- Consumes: new `archivum.db.graph.find_nodes(term, wiki_id, limit)`.
- Produces (graph.py):
  ```python
  async def find_nodes(term: str, wiki_id: str = "default", limit: int = 10) -> list[dict[str, Any]]:
      """Case-insensitive substring match over Page.title/slug and Entity.name.
      Returns [{id, label, node_type, wiki_id}]."""
  ```
- Produces (graph_seed.py):
  ```python
  async def graph_seed_search(
      query: str, *, wiki_id: str = "default", limit: int = 10,
      allowed: set[str] | None = None,
  ) -> list[RetrievalHit]:
      """Lexical-over-graph seeds as RetrievalHit(source="graph").
      score = 1.0 for exact label match else 0.5 substring."""
  ```

**Steps:**
- [ ] Write `test_find_nodes_matches_pages_and_entities` using `mock_kuzu_conn`:
  program the mock result to yield one Page row then one Entity row; assert
  `find_nodes` returns two dicts with correct `node_type` (`"page"`, `"entity"`).
- [ ] Run FAIL. Implement `graph.find_nodes` (two `CONTAINS(lower(...), lower($term))`
  queries against Page and Entity, wiki-filtered). Run PASS.
- [ ] Write `test_graph_seed_scores_exact_higher`: patch `graph.find_nodes` to return
  a node whose label equals the query and one substring match; assert exact match
  scores `1.0`. Run FAIL → implement `graph_seed.py` → PASS.
- [ ] Commit: `feat(retrieval): add graph-lexical seed retriever`.

---

### Task 6 — Fusion + ranking (reciprocal rank fusion)

**Files:** `archivum/retrieval/fusion.py` (new), `tests/test_retrieval_fusion.py` (new).

**Interfaces:**
- Consumes: `list[list[RetrievalHit]]` (per-source ranked lists).
- Produces:
  ```python
  def reciprocal_rank_fusion(
      ranked_lists: list[list[RetrievalHit]], *, k: int = 60, top_n: int = 3,
  ) -> list[RetrievalHit]:
      """RRF: score(node) = Σ 1/(k + rank_in_list). Merges duplicate node_ids
      (keeps best excerpt, unions source tags into `source` as comma-joined).
      Returns top_n seeds sorted by fused score desc, then node_id asc."""
  ```

**Steps:**
- [ ] Write `test_rrf_merges_and_ranks`: two lists; node `A` ranked 1st in both,
  node `B` 2nd in one; assert `A` first, `B` second, `top_n=3` returns both.
- [ ] Run FAIL. Implement RRF with stable tiebreak on `node_id`. Run PASS.
- [ ] Add `test_rrf_dedupes_across_sources`: same `node_id` from `"fts"` and
  `"vector"`; assert one merged hit whose `source == "fts,vector"` (sorted, joined)
  and fused score sums both contributions. Run PASS.
- [ ] Add `test_rrf_respects_top_n` (3 distinct nodes, `top_n=2` → 2 hits). Run PASS.
- [ ] Commit: `feat(retrieval): add reciprocal-rank fusion`.

---

### Task 7 — Source-type router

**Files:** `archivum/retrieval/router.py` (new), `tests/test_retrieval_router.py` (new).

**Interfaces:**
- Consumes: `SourceType`.
- Produces:
  ```python
  Retriever = Callable[..., Awaitable[list[RetrievalHit]]]

  def route(source_type: SourceType) -> list[Retriever]:
      """code / structured → [graph_seed_search, fts_search]  (NO vector).
      natural_language → [vector_search, graph_seed_search]."""
  def infer_source_type(query: str, hint: SourceType | None = None) -> SourceType:
      """Honor hint; else default NATURAL_LANGUAGE. Heuristic: query containing
      code punctuation like '()', '::', '/', '.py' → CODE."""
  ```

**Steps:**
- [ ] Write `test_route_code_excludes_vector`: assert `vector_search` NOT in
  `route(SourceType.CODE)`; assert `graph_seed_search` and `fts_search` present.
- [ ] Write `test_route_nl_includes_vector`: assert `vector_search` in
  `route(SourceType.NATURAL_LANGUAGE)`.
- [ ] Run FAIL. Implement `router.py` importing the three retriever fns. Run PASS.
- [ ] Add `test_infer_source_type_code_heuristic` (`"foo.bar()"` → `CODE`;
  `"what did we decide?"` → `NATURAL_LANGUAGE`; hint overrides). Run PASS.
- [ ] Commit: `feat(retrieval): add source-type routing (code=graph+lexical)`.

---

### Task 8 — BFS neighborhood builder

**Files:** `archivum/db/graph.py` (modify), `archivum/retrieval/bfs.py` (new),
`tests/test_retrieval_bfs.py` (new).

**Interfaces:**
- Consumes: `archivum.db.graph.get_neighbors(node_id, wiki_id)` (existing).
- Produces (bfs.py):
  ```python
  async def build_neighborhood(
      seeds: list[str], *, wiki_id: str = "default", depth: int = 2,
      max_nodes: int = 10, relations: set[str] | None = None,
      allowed: set[str] | None = None,
  ) -> tuple[list[ContextNode], list[ContextEdge], bool]:
      """Depth-limited BFS from seeds via graph.get_neighbors. Filters edges to
      `relations` if given. Caps at max_nodes (returns truncated=True when hit).
      Drops scope-disallowed nodes. Returns (nodes, edges, truncated)."""
  ```

**Steps:**
- [ ] Write `test_bfs_depth_limit`: patch `graph.get_neighbors` with a chain
  A→B→C→D; call `build_neighborhood(["A"], depth=2)`; assert D excluded, A/B/C present.
- [ ] Run FAIL. Implement BFS (visited set, queue of `(node_id, dist)`, stop at
  `depth`, map neighbor dicts → `ContextNode`/`ContextEdge`, default
  `extraction_method=EXTRACTED`, `confidence=1.0`). Run PASS.
- [ ] Add `test_bfs_max_nodes_truncates`: wide fan-out > `max_nodes=10`; assert
  `len(nodes) <= 10` and `truncated is True`. Run PASS.
- [ ] Add `test_bfs_relation_filter`: neighbors mix `references`/`mentions`, pass
  `relations={"references"}`; assert only `references` edges kept. Run PASS.
- [ ] Add `test_bfs_scope_drops_disallowed` (neighbor scope `"work"`, non-owner allowed set)
  → node absent. Run PASS.
- [ ] Commit: `feat(retrieval): add depth-limited BFS neighborhood builder`.

---

### Task 9 — Citation resolution (node → Source + span)

**Files:** `archivum/db/sqlite.py` (modify), `archivum/retrieval/citations.py` (new),
`tests/test_retrieval_citations.py` (new).

**Interfaces:**
- Produces (sqlite.py):
  ```python
  async def get_source_span(node_id: str, wiki_id: str = "default") -> dict[str, Any] | None:
      """Best-effort provenance lookup. If an L1 provenance/chunks table exists,
      return {source_id, source_type, title, origin_uri, chunk_id, span, excerpt}.
      Fallback: resolve node_id as a page slug → {source_id=slug,
      source_type="natural_language", title, origin_uri=None, chunk_id=None,
      span=None, excerpt=first 200 chars}. Returns None if unknown."""
  ```
- Produces (citations.py):
  ```python
  async def resolve_citations(
      nodes: list[ContextNode], *, wiki_id: str = "default",
  ) -> list[ContextNode]:
      """Populate node.citations via get_source_span. Nodes with no resolvable
      source get [] citations and confidence downgraded by 0.2 (min 0.1)."""
  ```

**Steps:**
- [ ] Write `test_get_source_span_page_fallback` with `mock_sqlite_db`: program
  `get_page`-style row; assert returned dict `source_type == "natural_language"`,
  `span is None`, `excerpt` present.
- [ ] Run FAIL. Implement `get_source_span` (try provenance query wrapped in
  try/except; on missing table or no row, fall back to `get_page`). Run PASS.
- [ ] Write `test_resolve_citations_attaches`: patch `get_source_span` to return a
  span dict; assert node gets one `Citation` with matching `source_id`.
- [ ] Write `test_resolve_citations_downgrades_unsourced`: patch to return `None`;
  assert `citations == []` and `confidence` dropped by `0.2`. Run FAIL → implement → PASS.
- [ ] Commit: `feat(retrieval): resolve node citations to Source+span`.

---

### Task 10 — Context package assembler

**Files:** `archivum/retrieval/package.py` (new), `tests/test_retrieval_package.py` (new).

**Interfaces:**
- Consumes: `build_neighborhood`, `resolve_citations`, seeds from a hits list.
- Produces:
  ```python
  async def build_context_package(
      query: str, seeds: list[RetrievalHit], *, wiki_id: str = "default",
      depth: int = 2, max_nodes: int = 10, relations: set[str] | None = None,
      allowed: set[str] | None = None,
  ) -> ContextPackage:
      """seeds → BFS neighborhood → resolve citations → ContextPackage.
      insufficient_evidence=True when no seeds OR no node carries a citation."""
  ```

**Steps:**
- [ ] Write `test_package_assembles_from_seeds`: patch `build_neighborhood` →
  (2 nodes, 1 edge, False) and `resolve_citations` → nodes-with-citations; assert
  `ContextPackage` has 2 nodes, 1 edge, `insufficient_evidence is False`, seeds set.
- [ ] Run FAIL. Implement `package.py`. Run PASS.
- [ ] Add `test_package_no_seeds_insufficient`: `seeds=[]` → `nodes==[]`,
  `insufficient_evidence is True` (no BFS call). Run PASS.
- [ ] Add `test_package_uncited_nodes_insufficient`: nodes all with empty citations
  → `insufficient_evidence is True`. Run PASS.
- [ ] Commit: `feat(retrieval): assemble scoped context packages`.

---

### Task 11 — Hybrid retriever orchestrator

**Files:** `archivum/retrieval/retriever.py` (new), `tests/test_retrieval_retriever.py` (new).

**Interfaces:**
- Consumes: `router.route`, `router.infer_source_type`, `reciprocal_rank_fusion`,
  `allowed_scopes`.
- Produces:
  ```python
  async def hybrid_retrieve(
      query: str, *, wiki_id: str = "default", user: CurrentUser | None = None,
      source_type: SourceType | None = None, limit: int = 10, top_n: int = 3,
      settings: Settings | None = None,
  ) -> list[RetrievalHit]:
      """Route by source type, run selected retrievers concurrently
      (asyncio.gather), fuse with RRF, return top_n seed hits. Passes the
      user's allowed scope-set to every retriever (owner → {"*"})."""
  ```

**Steps:**
- [ ] Write `test_hybrid_nl_calls_vector_and_graph`: patch `vector_search`,
  `graph_seed_search`, `fts_search` as AsyncMocks; call with NL query; assert
  `vector_search` awaited and `route`d set ran; assert fused hits returned.
- [ ] Run FAIL. Implement `hybrid_retrieve` (build `allowed` via `allowed_scopes`,
  `asyncio.gather` the routed retrievers with kwargs, RRF, return top_n). Run PASS.
- [ ] Add `test_hybrid_code_skips_vector`: `source_type=CODE`; assert `vector_search`
  mock **not** awaited (Global Constraint 2). Run PASS.
- [ ] Add `test_hybrid_owner_scope_wildcard`: owner user → each retriever received
  `allowed` containing `"*"`. Run PASS.
- [ ] Commit: `feat(retrieval): add hybrid retriever orchestrator`.

---

### Task 12 — Ask assembly + synthesis + insufficiency gate

**Files:** `archivum/retrieval/ask.py` (new), `tests/test_retrieval_ask.py` (new).

**Interfaces:**
- Consumes: `hybrid_retrieve`, `build_context_package`, existing LLM clients.
- Produces:
  ```python
  INSUFFICIENT_MSG = "insufficient evidence"

  def has_sufficient_support(pkg: ContextPackage, *, min_cited_nodes: int = 1,
                             min_confidence: float = 0.35) -> bool:
      """True iff pkg not flagged insufficient AND ≥min_cited_nodes nodes carry
      ≥1 citation AND max node confidence ≥ min_confidence."""

  def build_ask_prompt(question: str, pkg: ContextPackage) -> str:
      """Prompt instructing: answer ONLY from the cited context; if support is
      weak, reply exactly with the insufficient-evidence sentinel; cite [n]."""

  async def synthesize_answer(prompt: str, *, settings: Settings) -> str:
      """Route to anthropic / openrouter / openai_compat per
      settings.llm_synthesis_provider. Returns answer text."""

  async def assemble_ask(
      question: str, *, wiki_id: str = "default", user: CurrentUser | None = None,
      settings: Settings | None = None,
  ) -> AskResult:
      """Retrieve → package → gate. If not has_sufficient_support: return
      AskResult(answer=None, citations=[], insufficient_evidence=True,
      context_package=pkg) WITHOUT calling the LLM. Else synthesize, attach
      flattened citations from cited nodes."""
  ```

**Steps:**
- [ ] Write `test_has_sufficient_support_true_false`: a package with a cited node at
  confidence `0.9` → True; a package with only uncited/low-confidence nodes → False.
- [ ] Run FAIL. Implement `has_sufficient_support` + `build_ask_prompt`. Run PASS.
- [ ] Write **`test_assemble_ask_insufficient_no_llm`** (CRITICAL, spec §6.5): patch
  `hybrid_retrieve` → `[]`; patch `synthesize_answer` (AsyncMock). Assert result
  `insufficient_evidence is True`, `answer is None`, and `synthesize_answer` was
  **never awaited** (no fabrication). Run FAIL.
- [ ] Implement `assemble_ask` with the gate before synthesis. Run PASS.
- [ ] Write `test_assemble_ask_cited_answer`: patch `hybrid_retrieve` → one hit,
  `build_context_package` → package with a cited high-confidence node, and
  `synthesize_answer` → `"Alice leads X [1]."`; assert `insufficient_evidence is False`,
  `answer` set, `len(citations) >= 1`. Run PASS.
- [ ] Commit: `feat(retrieval): cited Ask with insufficient-evidence gate`.

---

### Task 13 — REST: /api/retrieve and /api/context-package

**Files:** `archivum/api/retrieval.py` (new), `tests/test_api_retrieval.py` (new).

**Interfaces:**
- Consumes: `hybrid_retrieve`, `build_context_package`, `get_current_user`, `get_settings`.
- Produces (router prefix `/api`, tag `retrieval`):
  ```python
  class RetrieveRequest(BaseModel):
      query: str
      source_type: SourceType | None = None
      limit: int = 10
      top_n: int = 3
  # POST /api/retrieve -> {"hits": list[RetrievalHit]}

  class ContextPackageRequest(BaseModel):
      query: str
      source_type: SourceType | None = None
      depth: int = 2
      max_nodes: int = 10
      relations: list[str] | None = None
  # POST /api/context-package -> ContextPackage
  ```

**Steps:**
- [ ] Write `test_retrieve_returns_hits` using `app_client`: patch
  `archivum.api.retrieval.hybrid_retrieve` → one `RetrievalHit`; POST with a
  bearer/cookie auth override; assert 200 and `body["hits"][0]["source"]` present.
  (Reuse the auth-dependency override pattern from existing API tests.)
- [ ] Run FAIL. Implement `retrieval.py` (validate non-empty query → 400
  `empty_query`; call orchestrators with `current_user`; JSON-serialize models via
  `.model_dump()`). Run PASS.
- [ ] Write `test_context_package_endpoint`: patch `build_context_package` →
  a package; assert 200 and `body["nodes"]` and `body["insufficient_evidence"] in (True, False)`.
  Run FAIL → wire second route → PASS.
- [ ] Add `test_retrieve_empty_query_400`. Run PASS.
- [ ] Commit: `feat(api): add /retrieve and /context-package routes`.

---

### Task 14 — REST: /api/ask (SSE, cited or insufficient)

**Files:** `archivum/api/ask.py` (new), `tests/test_api_ask.py` (new).

**Interfaces:**
- Consumes: `assemble_ask` (for the gate) + streaming LLM clients (mirrors
  `api/query.py` streaming). Produces (`EventSourceResponse`):
  ```python
  class AskRequest(BaseModel):
      question: str
  # POST /api/ask -> SSE:
  #   {"type":"citations","citations":[...]}          (always first)
  #   {"type":"token","token":"..."}*                 (only if sufficient)
  #   {"type":"insufficient","message":"insufficient evidence"}  (if weak)
  #   "[DONE]"
  ```

**Steps:**
- [ ] Write `test_ask_streams_insufficient` using `app_client`: patch
  `archivum.api.ask.assemble_ask` → `AskResult(insufficient_evidence=True,
  answer=None, citations=[], context_package=pkg)`; consume SSE; assert an
  `insufficient` event present, **no** `token` events, ends `[DONE]`.
- [ ] Run FAIL. Implement `ask.py`: call `assemble_ask` first; if insufficient, emit
  citations(empty)+insufficient+DONE without touching the LLM stream. Else emit
  citations, then stream tokens (reuse provider branches from `api/query.py`), then DONE.
  Enforce empty-question → 400. Run PASS.
- [ ] Write `test_ask_streams_cited_answer`: patch `assemble_ask` → sufficient with
  citations, patch the provider stream to yield two tokens; assert `citations`
  event then ≥1 `token` event then `[DONE]`. Run PASS.
- [ ] Commit: `feat(api): add cited /ask SSE endpoint`.

---

### Task 15 — REST: graph neighbors with depth

**Files:** `archivum/api/graph.py` (modify), `tests/test_api_graph_neighbors.py` (new).

**Interfaces:**
- Consumes: `build_neighborhood` (depth-aware).
- Produces: `GET /api/graph/neighbors?node_id=<id>&depth=<int>&wiki_id=<id>` →
  `{"center": node_id, "nodes": ContextNode[], "edges": ContextEdge[], "truncated": bool}`.
  (Keeps existing 1-hop `graph.get_neighbors` route intact; adds the depth-aware route.)

**Steps:**
- [ ] Write `test_graph_neighbors_depth` using `app_client`: patch
  `build_neighborhood` → (2 nodes, 1 edge, False); GET with `depth=2`; assert 200,
  `body["center"] == node_id`, `len(body["nodes"]) == 2`.
- [ ] Run FAIL. Add the route to `api/graph.py` (validate `depth` in 1..4 → else 400;
  pass `current_user` scope). Run PASS.
- [ ] Add `test_graph_neighbors_depth_bounds` (`depth=9` → 400). Run PASS.
- [ ] Commit: `feat(api): add depth-limited graph neighbors route`.

---

### Task 16 — Wire routers into the app

**Files:** `archivum/main.py` (modify), `tests/test_app_retrieval_wiring.py` (new).

**Interfaces:**
- Consumes: `api.retrieval.router`, `api.ask.router`.
- Produces: routes registered on the FastAPI app.

**Steps:**
- [ ] Write `test_routes_registered` using `app_client`: assert `/api/retrieve`,
  `/api/context-package`, `/api/ask`, `/api/graph/neighbors` appear in
  `{r.path for r in test_app.routes}` (access app via client).
- [ ] Run FAIL. Import and `app.include_router(...)` the new routers in
  `create_app()`. Run PASS.
- [ ] Commit: `feat(api): register retrieval and ask routers`.

---

### Task 17 — MCP tool: search (hybrid)

**Files:** `archivum/mcp/server.py` (modify), `tests/mcp_tests/test_retrieval_tools.py` (new).

**Interfaces:**
- Produces MCP tool:
  ```python
  @mcp.tool()
  async def search(query: str, source_type: str | None = None,
                   top_k: int = 5, wiki_id: str = "default") -> list[dict[str, Any]]:
      """Hybrid retrieval; returns RetrievalHit dicts (source-typed, scored)."""
  ```
  (Owner-scoped: MCP is single-owner; passes an owner `CurrentUser` → `allowed={"*"}`.)

**Steps:**
- [ ] Write `test_mcp_search_returns_hits`: `monkeypatch` `server.hybrid_retrieve`
  (AsyncMock) → `[RetrievalHit(...)]`; call `server.search("foo")`; assert list of
  dicts with `source` key.
- [ ] Run FAIL. Import `hybrid_retrieve`, `SourceType` into `server.py`; implement
  `search` (map `source_type` string → enum via `infer_source_type`;
  `.model_dump()` hits). Run PASS.
- [ ] Commit: `feat(mcp): add hybrid search tool`.

---

### Task 18 — MCP tool: get_context_package

**Files:** `archivum/mcp/server.py` (modify), `tests/mcp_tests/test_retrieval_tools.py` (extend).

**Interfaces:**
- Produces:
  ```python
  @mcp.tool()
  async def get_context_package(query: str, source_type: str | None = None,
                                depth: int = 2, max_nodes: int = 10,
                                wiki_id: str = "default") -> dict[str, Any]:
      """Seed → BFS → cited ContextPackage (primary agent output)."""
  ```

**Steps:**
- [ ] Write `test_mcp_context_package`: `monkeypatch` `server.hybrid_retrieve` →
  `[hit]` and `server.build_context_package` → a `ContextPackage`; call the tool;
  assert returned dict has `nodes`, `edges`, `insufficient_evidence`.
- [ ] Run FAIL. Implement tool (retrieve seeds then build package; `.model_dump()`).
  Run PASS.
- [ ] Commit: `feat(mcp): add get_context_package tool`.

---

### Task 19 — MCP tools: ask + graph_neighbors(depth)

**Files:** `archivum/mcp/server.py` (modify), `tests/mcp_tests/test_retrieval_tools.py` (extend).

**Interfaces:**
- Produces:
  ```python
  @mcp.tool()
  async def ask(question: str, wiki_id: str = "default") -> dict[str, Any]:
      """Cited answer or {'insufficient_evidence': True} (spec §6.5).
      Returns AskResult.model_dump()."""
  # Extend existing graph_neighbors with a depth param via build_neighborhood.
  ```

**Steps:**
- [ ] Write **`test_mcp_ask_insufficient`** (CRITICAL): `monkeypatch`
  `server.assemble_ask` → `AskResult(insufficient_evidence=True, answer=None,
  citations=[])`; call `server.ask("nonsense")`; assert
  `result["insufficient_evidence"] is True` and `result["answer"] is None`.
- [ ] Run FAIL. Import `assemble_ask`; implement `ask` tool. Run PASS.
- [ ] Write `test_mcp_ask_cited`: `assemble_ask` → sufficient with a citation;
  assert `result["answer"]` set and `result["citations"]` non-empty. Run PASS.
- [ ] Write `test_mcp_graph_neighbors_depth`: `monkeypatch` `build_neighborhood` →
  (nodes, edges, False); call `graph_neighbors("A", depth=2)`; assert `nodes`/`edges`
  present. Run FAIL → add `depth` param routing to `build_neighborhood` → PASS.
- [ ] Commit: `feat(mcp): add ask tool and depth-aware neighbors`.

---

### Task 20 — MCP write-back tool + scope note

**Files:** `archivum/mcp/server.py` (modify), `tests/mcp_tests/test_retrieval_tools.py` (extend).

**Interfaces:**
- Produces:
  ```python
  @mcp.tool()
  async def write_back(title: str, content: str, slug: str | None = None,
                       tags: list[str] | None = None,
                       wiki_id: str = "default") -> dict[str, Any]:
      """Agent write path: enqueues an L1 page write via the existing
      page_write_queue and returns the resulting page (delegates to write_page).
      Keeps L0 evidence immutable; writes land as regenerable content."""
  ```

**Steps:**
- [ ] Write `test_mcp_write_back_delegates`: `monkeypatch` `server.write_page`
  (AsyncMock) → a page dict; call `server.write_back("T", "C")`; assert
  `write_page` awaited with `title="T"` and the page dict returned.
- [ ] Run FAIL. Implement `write_back` delegating to existing `write_page`. Run PASS.
- [ ] Add `test_mcp_search_scope_owner`: assert `search` builds an owner
  `CurrentUser` so `allowed_scopes` yields `{"*"}` (patch `hybrid_retrieve`, inspect
  the `user` kwarg it received). Run PASS.
- [ ] Commit: `feat(mcp): add write-back tool and owner-scope wiring`.

---

## Self-Review

**Spec coverage.** §8 context packages: Tasks 1, 8, 10, 13, 18 (seeds→BFS→~5–10
capped nodes with edges + citation + method + confidence). §8 hybrid fusion (FTS +
Qdrant NL-only + Kuzu + temporal): Tasks 3, 4, 5, 6, 11 — **temporal filters** are
carried on `Citation`/node via bitemporal fields from L1; note: with PER-317 absent,
temporal filtering is a thin pass-through (nodes expose `confidence`/method now; a
`valid_from/valid_to` filter param is a follow-up once L1 exposes the columns —
flagged as an assumption, not silently dropped). §5/§7 code=graph+lexical, NL=vector:
Tasks 7, 11 (explicit `test_hybrid_code_skips_vector`). §6.5 insufficient-evidence:
Tasks 12, 14, 19 with dedicated CRITICAL tests asserting the LLM is never called.
§4 scope enforcement at query time: Tasks 2, 3, 4, 5, 8, 11, 20. §6.6 rebuildable:
retrieval reads L2/L1 only, never writes indexes. REST + MCP read/write surfaces:
Tasks 13–20. PER-320 Produces interfaces defined in Upstream Dependencies.

**Placeholder scan.** No `TODO`, no `...`, no `pass`-only bodies in interface
contracts. Every function has a signature, return type, and behavior description.
Temporal filtering gap is explicitly called out as an assumption tied to PER-317,
not a hidden placeholder.

**Type consistency.** `RetrievalHit`, `ContextNode`, `ContextEdge`, `Citation`,
`ContextPackage`, `AskResult`, `SourceType`, `ExtractionMethod` defined once in
Task 1 and reused verbatim downstream. `Retriever` alias in Task 7 matches the
async signatures of Tasks 3–5. `span: tuple[int,int] | None` serializes to a JSON
list — asserted in Task 1. Scope set type `set[str]` consistent across Tasks 2, 3,
4, 5, 8, 11. Router excludes `vector_search` for code in both the routing table
(Task 7) and the orchestrator test (Task 11), satisfying Global Constraint 2.
