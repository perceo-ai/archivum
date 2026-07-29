# Archivum Cross-Epic Interface Contract

**Status:** Canonical — single source of truth for cross-plan interfaces
**Date:** 2026-07-28
**Owner:** Pranav Kannepalli
**Anchors:** [Architecture spec](2026-07-28-archivum-architecture-design.md) (PER-314)

The 7 implementation plans (PER-315…321) were authored in parallel, so downstream
plans guessed at upstream interfaces. This document pins the **real** public
interfaces each epic PRODUCES, extracted from each plan's authoritative
"Interfaces / Produces" blocks and File Structure. Upstream names win.

Dependency chain: **315 → 316 → 317 → {318, 319} → 320; 321 depends on 319 + 320.**

Rule: a downstream plan MUST reference the exact symbol names listed here for the
epic it consumes. Where an upstream epic is not yet built, a downstream plan may
keep a test-time fake/shim, but the shim's note must name the real symbol it
stands in for.

---

## PER-315 — Immutable Source Store & Ingestion

Package: `apps/backend/archivum/store/`

### Types (`store/models.py`, `store/source_types.py`)
- `class SourceType(str, Enum)` — `DOCUMENT, WEB_PAGE, CONVERSATION, REPOSITORY, MESSAGE, MEDIA, TEST_RUN, DEPLOYMENT`.
- `class ExtractionMethod(str, Enum)` — `EXTRACTED, INFERRED, AMBIGUOUS`.
- `Source(id, content_hash, version, source_type, origin_uri, scope, ingested_at, recorded_at, valid_from, valid_to)` — frozen; `id` is uuid4 hex; `version: int`.
- `Document(id, source_id, mime, normalized_hash)` — frozen.
- `Chunk(id, document_id, seq, start_offset, end_offset, text_hash)` — frozen; offsets `int`, `end_offset` exclusive.
- `IngestResult(source, document, chunks, deduplicated)` — `chunks: list[Chunk]`, `deduplicated: bool`.
- `new_id() -> str`.

### L0 blob store (`store/blobs.py`)
- `class BlobStore` — `put(data: bytes) -> str`, `get(content_hash: str) -> bytes`, `exists(content_hash) -> bool`, `path_for(content_hash) -> Path`.
- `class BlobImmutabilityError(RuntimeError)`.

### Repository (`store/repository.py`)
- `class SourceStore` (async): `insert_source`, `insert_document`, `insert_chunk`, `get_source(id) -> Source | None`, `get_source_by_hash_and_version(content_hash, version) -> Source | None`, `latest_version_for_origin(origin_uri) -> int`, `get_document_for_source(source_id) -> Document | None`, `list_chunks(document_id) -> list[Chunk]`.

### Entrypoint (`store/ingest.py`)
- `async def ingest_source(*, origin_uri: str, raw_bytes: bytes, scope: str = "personal", explicit_type: SourceType | str | None = None, store: SourceStore | None = None, blob_store: BlobStore | None = None, settings: Settings | None = None) -> IngestResult`.

### SQLite tables (`store/schema.py`, `EVIDENCE_SCHEMA`, applied in `init_db`)
- `sources`, `documents`, `chunks` (spec §4 field set; `sources UNIQUE(content_hash, version)`, `chunks UNIQUE(document_id, seq)`).

### REST (`api/sources.py`, prefix `/api/sources`)
- `POST /api/sources/ingest` — body `SourceIngestRequest(origin_uri, scope="personal", source_type=None)` → `SourceResponse(id, content_hash, version, source_type, origin_uri, scope, deduplicated, chunk_count)`.
- `GET /api/sources/{source_id}` → `SourceDetailResponse(source, chunk_count)` or 404.

---

## PER-316 — Conversation & Agent Capture

Package: `apps/backend/archivum/capture/`

### Types (`capture/schema.py`)
- `Conversation(session_id, interface, started_at, turns, decisions=(), outcomes=(), scope="personal", origin_uri="", metadata={})` — frozen.
- `Turn(role, text, ts, tool_calls=())`, `ToolCall(name, arguments, result, call_id=None, started_at=None, ok=True)`, `Decision(statement, rationale="", turn_index=-1)`, `Outcome(task, status, detail="", turn_index=-1)`.
- `Role = Literal["user","assistant","tool","system"]`.

### Capture store (`capture/store.py`)
- `class CaptureStore` — `__init__(self, source_store: SourceStore)`; `async def capture(self, conv: Conversation) -> CaptureResult`. **Wraps PER-315 `SourceStore`.**
- `CaptureResult(source_id, content_hash, document_id, chunk_ids, created)` — frozen.

### Provenance (`capture/provenance.py`)
- `async def emit_knowledge(conv: Conversation, capture: CaptureResult) -> ProvenanceResult`.
- `ProvenanceResult(event_ids, claim_ids)` — frozen.

### DB CRUD (`db/capture_sql.py`)
- `init_capture_schema`, `insert_document`, `insert_chunk`, `insert_event`, `insert_claim`, `get_document_by_source`, `list_events_for_source`.

### SQLite tables (`db/capture_sql.py`, `CREATE TABLE IF NOT EXISTS`)
- `events`, `claims` (adds to PER-315's `sources`/`documents`/`chunks`; DDL is `IF NOT EXISTS`-safe).

### MCP (`mcp/server.py`)
- Tool `capture_conversation(session_id, interface, turns, scope="personal") -> dict`.

---

## PER-317 — Provenance-Aware Graph Construction

Package: `apps/backend/archivum/graph/`

### Candidate types (`graph/types.py`) — the write-path input contract
- `class ObjectKind(str, Enum)` — `ENTITY, ARTIFACT, EVENT, CLAIM`.
- `class ExtractionMethod(str, Enum)` — `EXTRACTED, INFERRED, AMBIGUOUS`.
- `EvidenceSpan(chunk_id, span_start, span_end)` — frozen.
- `CandidateObject(kind, scope, label, extraction_method, confidence, producer, evidence, subtype=None, attrs={}, valid_from=None, valid_to=None, recorded_at=None, content_key=None)` — frozen.
- `CandidateRelationship(rel_type, from_ref, to_ref, scope, extraction_method, confidence, producer, evidence, attrs={}, valid_from=None, valid_to=None, recorded_at=None)` — frozen.
- `CandidateBatch(objects, relationships, source_id, document_id)` — frozen.

### Validation & write API
- `graph/validation.py`: `class ValidationLayer` — `async validate_object(obj)`, `async validate_relationship(rel, known_refs)`, `async validate_batch(batch: CandidateBatch) -> None`. `class ValidationError(Exception)`.
- `graph/resolution.py`: `async def upsert_object(obj: CandidateObject) -> str`; `async def resolve_object(obj) -> ResolutionResult`.
- `graph/store.py`: `async def insert_object(obj: CandidateObject) -> str`; `async def insert_relationship(rel: CandidateRelationship, ref_to_id: dict[str, str]) -> str`.

### Read API (`graph/store.py`)
- `async def get_object(id: str) -> dict | None`.
- `async def list_objects(kind: str | None = None, scope: str | None = None) -> list[dict]`.
- `async def find_objects_by_content_key(content_key, scope) -> list[dict]`.

### Index rebuild (`graph/projectors.py`)
- `async def rebuild_indexes(targets: set[str] | None = None) -> dict[str, dict]` — `targets ⊆ {"kuzu","qdrant","fts"}`.

### SQLite tables (`graph/schema.py`, `KNOWLEDGE_SCHEMA`)
- `knowledge_objects`, `relationships`, `provenance` (`object_id, object_table, chunk_id, span_start, span_end, extraction_method`), `supersession`, `graph_work_queue`, `extraction_cache`, `prompt_fingerprint_cache`, FTS5 `knowledge_fts`.

### Consumes from upstream (canonical)
- PER-315 `ingest_source()` / `SourceStore` and tables `sources`/`documents`/`chunks`.
- PER-316 `CaptureStore.capture()` and `provenance.emit_knowledge()` (agent sessions land as Sources feeding the work queue).

---

## PER-318 — Archgraph Developer Intelligence

Package: `apps/backend/archivum/archgraph/`

### Code model (`archgraph/models.py`)
- `CodeNode(id, label, kind, source_file, source_location)`, `CodeEdge(source, target, relation, method, source_file, source_location, confidence=1.0)`, `Extraction(nodes, edges, error=None)` — all frozen.
- `class ExtractionMethod(str, Enum)` — `EXTRACTED, INFERRED, AMBIGUOUS`.

### Code retrieval (`archgraph/retrieval.py`) — CANONICAL name
- `@dataclass class ScopedSubgraph` — `nodes: list[dict]` (each: `id, label, kind, scope, confidence, extraction_method, citation`), `edges: list[dict]` (each: `source, target, relation, extraction_method, confidence`).
- `async def retrieve_code(conn, query: str, *, depth: int = 2, max_nodes: int = 10, scope: str | None = None, relations: frozenset[str] | None = None) -> ScopedSubgraph`.

### Ingestion (`archgraph/ingest.py`)
- `async def ingest_repo(conn, root, *, scope, cache_dir, update=False) -> IngestReport`; `IngestReport(files, nodes, edges, rejected, cache_hits)`.

### SQLite tables (`archgraph/lexical.py`)
- `code_trigram(trigram, node_id)`, `code_node_text(node_id, text)`.

### `__init__.py` re-exports
- `ingest_repo`, `retrieve_code`, `ScopedSubgraph`, `ExtractionMethod`.

### Consumes from upstream (canonical)
- PER-317 write path: `CandidateObject`/`CandidateRelationship`/`CandidateBatch` → `ValidationLayer.validate_batch()` → `upsert_object()` / `insert_relationship()`; index refresh via `rebuild_indexes(targets)`; reads via `get_object` / `list_objects`. Code provenance anchors to a PER-315 `Chunk` (evidence span).

---

## PER-319 — Cited Retrieval, Ask & MCP

Package: `apps/backend/archivum/retrieval/` + `api/` + `mcp/`

### Types (`retrieval/models.py`, Pydantic)
- `Citation(source_id, source_type, title, origin_uri=None, chunk_id=None, span=None, excerpt=None)`.
- `ContextNode(id, label, node_type, scope="personal", extraction_method=EXTRACTED, confidence=1.0, citations=[])`.
- `ContextEdge(from_id, to_id, relation, extraction_method=EXTRACTED, confidence=1.0)`.
- `ContextPackage(query, seeds, nodes, edges, truncated=False, insufficient_evidence=False)`.
- `RetrievalHit(node_id, label, node_type, scope="personal", score, source, excerpt=None)`.
- `AskResult(answer, citations, insufficient_evidence=False, context_package=None)`.
- `class SourceType(str, Enum)` — `CODE, STRUCTURED, NATURAL_LANGUAGE`.

### REST routes (`api/retrieval.py`, `api/ask.py`, `api/graph.py`) — CANONICAL
- `POST /api/retrieve` — body `RetrieveRequest(query, source_type=None, limit=10, top_n=3)` → `{ "hits": RetrievalHit[] }`.
- `POST /api/context-package` — body `ContextPackageRequest(query, source_type=None, depth=2, max_nodes=10, relations=None)` → `ContextPackage`.
- `POST /api/ask` — body `AskRequest(question)` → **SSE stream**: `citations` event → `token`* events → `insufficient` event (when weak) → `[DONE]`.
- `GET /api/graph/neighbors?node_id=<id>&depth=<int>&wiki_id=<id>` → `{ center, nodes, edges }`.

### Core functions (`retrieval/`)
- `async hybrid_retrieve(...) -> list[RetrievalHit]`, `async build_context_package(...) -> ContextPackage`, `async assemble_ask(...) -> AskResult`, `has_sufficient_support(pkg, ...) -> bool`.

### MCP tools (`mcp/server.py`)
- `search(query, source_type=None, top_k=5, wiki_id="default")`, `get_context_package(...)`, `ask(question, wiki_id="default")` (returns `AskResult.model_dump()`), `graph_neighbors` (extended with `depth`), `write_back(...)`.

### Consumes from upstream (canonical)
- PER-318 code path: `retrieve_code(...) -> ScopedSubgraph` (the `CODE_SEARCH` router slot).
- PER-317 citations/provenance: `get_object` + the `provenance` table (`chunk_id` + span) for citation resolution; `knowledge_objects`/`relationships` for neighborhood BFS.

---

## PER-320 — Standalone Product Experience

Frontend (`apps/frontend/`). Consumes PER-319's REST layer only. All API drift is
isolated to `src/api/types.ts` + the URL strings in `src/api/knowledge.ts`.

### Consumes from upstream (canonical — align to PER-319 real routes/types)
- `POST /api/ask` — SSE events `citations`, `token`, `insufficient`, `[DONE]` (there is **no** `context` event; obtain the package via `POST /api/context-package`).
- `POST /api/retrieve` → `{ hits: RetrievalHit[] }`.
- `POST /api/context-package` → `ContextPackage`.
- `GET /api/graph/neighbors?node_id=&depth=` → `{ center, nodes, edges }`.
- `GET /api/sources?...` / `GET /api/sources/{id}` — read-back from PER-315 `api/sources.py`.
- Shared types: `ContextPackage`, `Citation`, `ContextNode`, `ContextEdge`, `RetrievalHit`, `AskResult` — mirror PER-319 field lists in `src/api/types.ts`.

---

## PER-321 — Hardening, Privacy & Dogfooding

Ops/backend hardening. Consumes PER-319 retrieval + PER-320 deployment surface.

### Consumes from upstream (canonical — align to PER-319)
- Retrieval via `build_context_package(...) -> ContextPackage` / `assemble_ask(...) -> AskResult`; the "insufficient evidence" path is PER-319's `has_sufficient_support` + the SSE `insufficient` event (not a home-grown boolean).
- `POST /api/context-package` → `ContextPackage` and `POST /api/ask` for the eval harness.
- The Task 8 `retrieval.scoped_page_search` shim is a **test-time stand-in for PER-319 `hybrid_retrieve` / `build_context_package`**; on landing, re-point at those and adapt callers from `list[dict]` to `RetrievalHit`/`ContextPackage`.

---

## Reconciliation notes

Mismatches found across the parallel plans and the canonical name chosen:

1. **Code-retrieval function name.** PER-318 produces `retrieve_code(...) -> ScopedSubgraph`; PER-319 guessed `code_retrieve(seed, scope)` returning an unnamed "scoped code subgraph". **Canonical: `retrieve_code` → `ScopedSubgraph`.** Fix PER-319.

2. **PER-317 write API.** PER-318 invented `write_candidates(conn, candidates) -> WriteResult`, a `Candidate = CandidateEntity | CandidateArtifact | CandidateRelationship` union, and a `FakeValidationLayer` + `archgraph/mapper.py` adapter. PER-317 really produces `CandidateObject`/`CandidateRelationship`/`CandidateBatch` → `ValidationLayer.validate_batch()` → `upsert_object()` / `insert_relationship()`, plus `rebuild_indexes(targets)` and reads `get_object`/`list_objects`. **Canonical: PER-317's names.** PER-318's mapper now targets `CandidateObject`/`CandidateRelationship`/`CandidateBatch`; the retained test fake mocks `ValidationLayer.validate_batch`.

3. **PER-317's guessed L1 evidence shape.** PER-317 guessed a `sources`/`documents`/`chunks` column set + a `seed_l1_base` fixture and an `on_session_captured` no-op. **Canonical upstream: PER-315 `ingest_source()`/`SourceStore` + tables `sources`/`documents`/`chunks`; PER-316 `CaptureStore.capture()` / `provenance.emit_knowledge()`.** Fixture kept as a test-time stand-in for PER-315's `EVIDENCE_SCHEMA`; `on_session_captured` documented as standing in for `CaptureStore.capture`.

4. **PER-316 upstream name.** PER-316 correctly wraps PER-315 `SourceStore.put`; its `_SqliteSourceStore` is a documented test fallback for `SourceStore`. Provenance emit is `emit_knowledge` (matches). No rename needed.

5. **PER-319 citation/provenance source.** PER-319 referenced only an unnamed "L1 provenance/chunks table" + its own `get_source_span` helper. **Canonical: PER-317 `get_object` + the `provenance` table** back `get_source_span`; the helper is kept as the local adapter but noted to read PER-317's `provenance`.

6. **PER-320 endpoint shapes.** PER-320 invented `/api/sources`, `/api/entities`, `/api/timeline`, a wrong `/api/graph?seed=&relations=` route, and an `/api/ask` `context` SSE event. **Canonical: PER-319's real routes** (`/api/retrieve`, `/api/context-package`, `/api/ask` SSE without a `context` event, `/api/graph/neighbors?node_id=&depth=`) and PER-315's `/api/sources`. Type mirrors align to `ContextPackage`/`Citation`/`RetrievalHit`/`AskResult`.

7. **PER-321 endpoint shapes.** PER-321's `scoped_page_search -> list[dict]` shim diverges from PER-319. **Canonical: PER-319 `hybrid_retrieve`/`build_context_package` returning `RetrievalHit`/`ContextPackage`**; shim retained as a labelled stand-in.
