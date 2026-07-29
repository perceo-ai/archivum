# PER-317: Provenance-Aware Knowledge Graph Construction — Implementation Plan

**For agentic workers:** Execute tasks in order. Each task is self-contained, follows strict TDD (write a failing pytest against real code → run it and observe the expected FAIL → write the minimal real implementation → run it and observe PASS → commit with the exact conventional-commit message given). Steps are sized 2–5 minutes. There are NO placeholders: every symbol referenced in a step is defined in some task. Do not stub, do not `pass`, do not `TODO`. If a type is used before it is defined, that is a bug in this plan — stop and re-read Upstream Dependencies.

---

## Goal

Build the L1 knowledge-graph layer of Archivum: extract and maintain `Entity` / `Artifact` / `Event` / `Claim` / `Relationship` objects from captured sources, where **every** generated object retains its supporting evidence (a chunk span), an `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`, a numeric `confidence`, a `scope`, and bitemporal validity (`valid_from` / `valid_to` / `recorded_at`). Implement the agent-worker stage from spec §5 (PTY-hosted workers pulling a work queue, emitting candidates through a validation layer into L1), support incremental updates, contradiction detection with supersession, and rebuildable L2 indexes (Kuzu graph + Qdrant vectors + SQLite FTS) all derived from L1.

This epic owns the **write path into L1** and the **projection out of L1 into L2**. Downstream: PER-318 (Archgraph) plugs a deterministic code producer into the same validation layer + candidate write API; PER-319 reads the rebuilt indexes.

---

## Architecture

```
sources/documents/chunks (L1, from PER-315)
        │
        ▼
  work queue (graph_work_queue table)  ◄── enqueue on new/changed Document
        │
        ▼
  agent-worker harness (PTY-hosted worker OR deterministic MockWorker)
        │  emits Candidate* objects (evidence span + method + confidence + scope)
        ▼
  VALIDATION LAYER  ── enforces §4 invariants (≥1 evidence, method∈enum, 0≤conf≤1, scope set, bitemporal coherent)
        │  valid candidates only
        ▼
  WRITE PATH  ── entity resolution/dedup → contradiction detection → supersession edges → L1 insert
        │
        ▼
  L1 canonical tables (entities/artifacts/events/claims/relationships + provenance/supersession)
        │
        ▼
  INDEX PROJECTORS  ── rebuild_indexes() drops & rebuilds Kuzu + Qdrant + FTS from L1
        │
        ▼
  L2 derived indexes (read by PER-319)
```

Caching sits beside the worker stage: an **AST/content-hash cache** (skip re-extraction when a Document's `content_hash` + extractor version is unchanged) and a **semantic prompt-fingerprint cache** (skip LLM billing when the prompt fingerprint has a stored result, surviving extractor-version bumps).

---

## Tech Stack

- **Language:** Python 3.12, `from __future__ import annotations` in every module.
- **Async:** `asyncio`, `aiosqlite` (matches `archivum/db/sqlite.py`). Kuzu calls wrapped in `run_in_executor` (matches `archivum/db/graph.py`).
- **Web:** FastAPI (existing app in `archivum/main.py`).
- **Stores:** SQLite (L1, store of record), Qdrant (`archivum/db/qdrant_client.py`), Kuzu (`archivum/db/graph.py`), SQLite FTS5.
- **Testing:** `pytest>=9`, `pytest-asyncio>=1.4`. Async tests use `@pytest.mark.asyncio`. A `conftest.py` (Task 1) points every store at a `tmp_path` sandbox so tests never touch real volumes.
- **PTY:** stdlib `pty` + `asyncio` subprocess for the worker harness.
- **Hashing:** stdlib `hashlib.sha256`.

---

## Global Constraints

These derive from spec §2, §4, §6 and hold for **every** task. A change that violates one is wrong even if tests pass.

1. **L1 is canonical.** The SQLite L1 tables are the only source of truth for knowledge objects. Nothing reads knowledge from Kuzu/Qdrant/FTS as truth.
2. **Indexes are rebuildable.** Any L2 index (Kuzu, Qdrant, FTS) can be dropped and fully reconstructed from L1 by `rebuild_indexes()` with no data loss. No projector may hold state absent from L1.
3. **Every object cites evidence + confidence + method.** Every `Entity`/`Artifact`/`Event`/`Claim`/`Relationship` row has ≥1 provenance link (`chunk_id` + span), a `confidence` in `[0,1]`, and an `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`. The validation layer rejects any candidate lacking these. An object with no evidence cannot exist in L1.
4. **Contradictions are modeled, never overwritten.** A newer high-confidence claim that contradicts an older one creates `supersedes` / `superseded_by` edges. Both rows remain in L1 and remain queryable with their temporal validity. No UPDATE/DELETE silently discards a contested fact.
5. **Evolve in place.** Reuse existing modules (`db/sqlite.py`, `db/graph.py`, `db/qdrant_client.py`) and conventions (async functions, `get_db()`, `run_in_executor`). Add new modules under `archivum/graph/`; do not rewrite the existing stack.
6. **Bitemporal.** `valid_from`/`valid_to` describe world-time; `recorded_at` describes when Archivum learned it. These are distinct and both stored on knowledge objects.
7. **Scope on everything.** Every knowledge object carries a `scope` string (e.g. `personal`, `work`, `repo:archivum`). Enforced at query time downstream; stored here.

---

## File Structure

```
apps/backend/
  archivum/
    graph/
      __init__.py
      schema.py            # Task 2  — L1 DDL for knowledge objects + provenance + supersession
      types.py             # Task 3  — Candidate* dataclasses + enums (ExtractionMethod, ...)
      provenance.py        # Task 4  — Evidence/provenance dataclass + resolution against chunks
      validation.py        # Task 5  — ValidationLayer: enforce §4 invariants; ValidationError
      store.py             # Task 6+ — L1 read/write CRUD for knowledge objects (candidate write API)
      resolution.py        # Task 8  — entity resolution / dedup
      contradiction.py     # Task 9  — contradiction detection + supersession edge creation
      temporal.py          # Task 10 — bitemporal helpers (interval overlap, close-out)
      queue.py             # Task 11 — graph_work_queue enqueue/claim/complete/fail
      worker.py            # Task 13 — WorkerProtocol + PtyWorkerHarness
      mock_worker.py       # Task 12 — deterministic MockWorker for tests
      pipeline.py          # Task 14 — end-to-end: claim job → worker → validate → write
      cache.py             # Task 15 — content-hash + prompt-fingerprint caches
      projectors.py        # Task 16-18 — Kuzu/Qdrant/FTS projectors + rebuild_indexes()
      update.py            # Task 19 — --update incremental re-extraction + dangling-edge pruning
      cli.py               # Task 20 — CLI: graph rebuild-indexes / graph update
  tests/
    conftest.py            # Task 1
    graph/
      __init__.py
      test_schema.py       # Task 2
      test_types.py        # Task 3
      test_provenance.py   # Task 4
      test_validation.py   # Task 5
      test_store.py        # Task 6,7
      test_resolution.py   # Task 8
      test_contradiction.py# Task 9
      test_temporal.py     # Task 10
      test_queue.py        # Task 11
      test_mock_worker.py  # Task 12
      test_worker.py       # Task 13
      test_pipeline.py     # Task 14
      test_cache.py        # Task 15
      test_projectors.py   # Task 16,17,18
      test_rebuild.py      # Task 18
      test_update.py       # Task 19
      test_cli.py          # Task 20
```

---

## Upstream Dependencies

**Canonical upstream interfaces are defined in [2026-07-28-archivum-interface-contract.md](2026-07-28-archivum-interface-contract.md).** This plan consumes PER-315's real L0/L1 surface and PER-316's real capture surface:

- **PER-315 `SourceStore`** (`archivum/store/repository.py`) — async CRUD over L1; not directly written here, read for evidence resolution.
- **PER-315 `ingest_source(...)`** (`archivum/store/ingest.py`) — deterministic-stage ingestion producing `sources`, `documents`, `chunks` rows; upstream of this plan's work queue, not directly called here.
- **PER-315 L1 base tables** (real schema, `archivum/store/schema.py::EVIDENCE_SCHEMA`, applied in `init_db`):

  ```sql
  sources(id TEXT PRIMARY KEY, content_hash TEXT, version INTEGER,
          source_type TEXT, origin_uri TEXT, scope TEXT,
          ingested_at TEXT, recorded_at TEXT, valid_from TEXT, valid_to TEXT,
          UNIQUE(content_hash, version))
  documents(id TEXT PRIMARY KEY, source_id TEXT REFERENCES sources(id),
            mime TEXT, normalized_hash TEXT)
  chunks(id TEXT PRIMARY KEY, document_id TEXT REFERENCES documents(id),
         seq INTEGER, start_offset INTEGER, end_offset INTEGER, text_hash TEXT,
         UNIQUE(document_id, seq))
  ```

  **TEST STAND-IN (flagged):** Task 1's `conftest.py` fixture `seed_l1_base(...)` stands in for PER-315's `EVIDENCE_SCHEMA` so PER-317 tests are self-contained. When PER-315 lands, delete the fixture's DDL and import `archivum.store.schema.EVIDENCE_SCHEMA` (via `init_db`) instead — the columns above are PER-315's real contract.

- **PER-316** captures each agent session as a Source via **`CaptureStore.capture(conv) -> CaptureResult`** and emits knowledge via **`provenance.emit_knowledge(conv, capture) -> ProvenanceResult`** (`archivum/capture/`); those captured Sources feed this plan's work queue. This plan's worker harness (Task 13) exposes a session-capture hook point (`on_session_captured`) that stands in for `CaptureStore.capture`; it is a no-op callback by default until PER-316 is wired in.

**Existing modules consumed as-is:** `archivum.config.get_settings`, `archivum.db.sqlite.get_db`, `archivum.db.graph` (`_get_conn`, `_run`), `archivum.db.qdrant_client` (`get_client`, `embed_texts`, `resolve_embed_dim`).

---

### Task 1 — Test sandbox & L1 base fixtures

**Files:** `tests/conftest.py`, `tests/graph/__init__.py`, `archivum/graph/__init__.py`

**Interfaces:**
- Produces fixture `graph_db(tmp_path, monkeypatch)` → configures `archivum.db.sqlite` to use `tmp_path/l1.db` and yields nothing (side-effect: `get_db()` now points at the sandbox).
- Produces fixture `seed_l1_base()` → async callable inserting `sources`/`documents`/`chunks` rows; returns `dict` of created ids.

- [ ] Create empty `archivum/graph/__init__.py` and `tests/graph/__init__.py`. Commit: `chore(graph): scaffold graph package and test dir`.
- [ ] In `tests/conftest.py`, write a **failing** test-support import test in `tests/graph/test_schema.py` first? No — instead write `conftest.py` fixture `graph_db` that calls `archivum.db.sqlite.configure(Settings(db_path=tmp_path/'l1.db', ...))`. Add a smoke test `test_sandbox_db_is_isolated` in `tests/graph/test_schema.py` asserting `get_settings` unaffected and the sandbox file is created after `init_db`.
- [ ] Run `pytest tests/graph/test_schema.py::test_sandbox_db_is_isolated` → expect **FAIL** (fixture/DDL not wired).
- [ ] Implement `graph_db` fixture: build a `Settings` with `db_path`, `kuzu_path`, `qdrant_url` pointing under `tmp_path` (Qdrant uses `:memory:` via `AsyncQdrantClient(location=":memory:")` — override in fixture by monkeypatching `qdrant_client.get_client`). Implement `seed_l1_base` as an async fixture-factory inserting one source, one document, two chunks using the column contract from Upstream Dependencies. Add DDL for the three base tables inside the fixture (flagged assumption).
- [ ] Run the smoke test → expect **PASS**.
- [ ] Commit: `test(graph): add L1 sandbox and base-table fixtures`.

---

### Task 2 — L1 knowledge-object schema (DDL + migration)

**Files:** `archivum/graph/schema.py`, `tests/graph/test_schema.py`

**Interfaces:**
- Produces `KNOWLEDGE_SCHEMA: str` (DDL) and `async def init_knowledge_schema() -> None`.
- Tables: `knowledge_objects` (unified table with `kind ∈ {entity,artifact,event,claim}`), `relationships`, `provenance`, `supersession`.

Columns on `knowledge_objects`: `id TEXT PK`, `kind TEXT`, `scope TEXT NOT NULL`, `label TEXT`, `subtype TEXT`, `attrs TEXT DEFAULT '{}'` (JSON), `extraction_method TEXT NOT NULL`, `confidence REAL NOT NULL`, `producer TEXT NOT NULL`, `valid_from TEXT`, `valid_to TEXT`, `recorded_at TEXT NOT NULL`, `content_key TEXT` (dedup key), `created_at TEXT`.
`relationships`: `id TEXT PK`, `from_id TEXT`, `to_id TEXT`, `rel_type TEXT`, `scope`, `extraction_method`, `confidence`, `producer`, `valid_from`, `valid_to`, `recorded_at`, `attrs`.
`provenance`: `id TEXT PK`, `object_id TEXT` (FK to knowledge_objects.id OR relationships.id), `object_table TEXT`, `chunk_id TEXT`, `span_start INTEGER`, `span_end INTEGER`, `extraction_method TEXT`.
`supersession`: `id TEXT PK`, `superseded_id TEXT`, `superseding_id TEXT`, `object_table TEXT`, `reason TEXT`, `recorded_at TEXT`.

- [ ] Write **failing** `test_init_knowledge_schema_creates_tables` in `tests/graph/test_schema.py`: after `await init_knowledge_schema()`, query `sqlite_master` and assert the four table names exist and that `knowledge_objects` has a `CHECK(extraction_method IN ('EXTRACTED','INFERRED','AMBIGUOUS'))` and `CHECK(confidence>=0 AND confidence<=1)` (assert by inserting an out-of-range row raises `sqlite3.IntegrityError`).
- [ ] Run → **FAIL** (module missing).
- [ ] Implement `schema.py`: define `KNOWLEDGE_SCHEMA` with the four `CREATE TABLE IF NOT EXISTS` + the two CHECK constraints + indexes (`idx_ko_kind_scope`, `idx_prov_object`, `idx_rel_from`, `idx_rel_to`, `idx_supersession_superseded`). Implement `init_knowledge_schema()` using `get_db()` + `executescript` (mirror `sqlite.init_db`).
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): add L1 knowledge-object schema and migration`.

---

### Task 3 — Candidate types & enums (the write-API value objects)

**Files:** `archivum/graph/types.py`, `tests/graph/test_types.py`

**Interfaces (this is the core contract PER-318 produces and the validation layer consumes):**

```python
class ExtractionMethod(str, Enum):
    EXTRACTED = "EXTRACTED"; INFERRED = "INFERRED"; AMBIGUOUS = "AMBIGUOUS"

class ObjectKind(str, Enum):
    ENTITY = "entity"; ARTIFACT = "artifact"; EVENT = "event"; CLAIM = "claim"

@dataclass(frozen=True)
class EvidenceSpan:
    chunk_id: str; span_start: int; span_end: int

@dataclass(frozen=True)
class CandidateObject:
    kind: ObjectKind
    scope: str
    label: str
    extraction_method: ExtractionMethod
    confidence: float
    producer: str
    evidence: list[EvidenceSpan]              # ≥1 required
    subtype: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)
    valid_from: str | None = None
    valid_to: str | None = None
    recorded_at: str | None = None            # defaulted to now() at write time
    content_key: str | None = None            # dedup key; derived if None

@dataclass(frozen=True)
class CandidateRelationship:
    rel_type: str
    from_ref: str        # content_key or object id of source
    to_ref: str
    scope: str
    extraction_method: ExtractionMethod
    confidence: float
    producer: str
    evidence: list[EvidenceSpan]              # ≥1 required
    attrs: dict[str, Any] = field(default_factory=dict)
    valid_from: str | None = None
    valid_to: str | None = None
    recorded_at: str | None = None

@dataclass(frozen=True)
class CandidateBatch:
    objects: list[CandidateObject]
    relationships: list[CandidateRelationship]
    source_id: str
    document_id: str
```

- [ ] Write **failing** `test_candidate_object_defaults_and_frozen` and `test_extraction_method_enum_values`: build a `CandidateObject`, assert defaults (`attrs=={}`, `evidence` required positionally), assert immutability raises `FrozenInstanceError` on attribute set, assert `ExtractionMethod("INFERRED")` round-trips.
- [ ] Run → **FAIL**.
- [ ] Implement `types.py` exactly as above with `from __future__ import annotations`, `dataclasses`, `enum`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): add candidate object/relationship value types`.

---

### Task 4 — Provenance resolution against chunks

**Files:** `archivum/graph/provenance.py`, `tests/graph/test_provenance.py`

**Interfaces:**
- Consumes `EvidenceSpan`, base `chunks` table.
- Produces `async def resolve_evidence(evidence: list[EvidenceSpan]) -> list[ResolvedEvidence]` and `@dataclass ResolvedEvidence(chunk_id, span_start, span_end, chunk_text_len, document_id)`.
- Raises `DanglingEvidenceError` when a `chunk_id` does not exist, or the span lies outside the chunk's `[0, text_len]`.

- [ ] Write **failing** tests using `graph_db`+`seed_l1_base`: `test_resolve_evidence_ok` (valid chunk + in-range span → `ResolvedEvidence` with correct `document_id`), `test_resolve_evidence_missing_chunk_raises`, `test_resolve_evidence_out_of_range_span_raises`.
- [ ] Run → **FAIL**.
- [ ] Implement `provenance.py`: for each span, `SELECT id, document_id, length(text) FROM chunks WHERE id=?`; raise `DanglingEvidenceError` if missing or `span_end > len` or `span_start < 0` or `span_start > span_end`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): resolve and bounds-check evidence spans against chunks`.

---

### Task 5 — Validation layer (enforces §4 invariants)

**Files:** `archivum/graph/validation.py`, `tests/graph/test_validation.py`

**Interfaces (the gate every producer — worker AND PER-318 — passes through):**
- Produces `class ValidationError(Exception)` and `class ValidationLayer` with:
  - `async def validate_object(self, obj: CandidateObject) -> None`
  - `async def validate_relationship(self, rel: CandidateRelationship, known_refs: set[str]) -> None`
  - `async def validate_batch(self, batch: CandidateBatch) -> None`
- Invariants enforced (each a distinct raise, distinct message prefix): `evidence-required` (≥1), `evidence-resolves` (via `resolve_evidence`), `method-enum`, `confidence-range` (0≤c≤1), `scope-required` (non-empty), `bitemporal-coherent` (`valid_from`≤`valid_to` when both set), `relationship-refs-known` (both `from_ref`/`to_ref` in `known_refs`).

- [ ] Write **failing** tests: `test_valid_object_passes`, `test_object_missing_evidence_raises`, `test_confidence_out_of_range_raises`, `test_empty_scope_raises`, `test_bad_bitemporal_raises`, `test_relationship_unknown_ref_raises`, `test_dangling_evidence_bubbles_as_validation_error` (wrap `DanglingEvidenceError` into `ValidationError`).
- [ ] Run → **FAIL**.
- [ ] Implement `validation.py`. `validate_object` checks evidence non-empty, calls `resolve_evidence` (catch `DanglingEvidenceError` → `ValidationError("evidence-resolves: ...")`), checks `0<=confidence<=1`, `scope.strip()`, bitemporal order. `validate_batch` builds `known_refs = {o.content_key or derive_content_key(o) for o in objects}` then validates each object and each relationship against it.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): validation layer enforcing L1 provenance invariants`.

---

### Task 6 — L1 store: content-key derivation + object write

**Files:** `archivum/graph/store.py`, `tests/graph/test_store.py`

**Interfaces (candidate write API, part 1):**
- Produces `def derive_content_key(kind, scope, label, subtype) -> str` (sha256 of normalized tuple).
- Produces `async def insert_object(obj: CandidateObject) -> str` → returns new `id` (uuid4 hex). Writes the `knowledge_objects` row + its `provenance` rows in one transaction. Fills `recorded_at`/`content_key` defaults.

- [ ] Write **failing** tests: `test_derive_content_key_stable` (same inputs → same key; label case/space-normalized), `test_insert_object_persists_row_and_provenance` (insert, then `SELECT` back the object row and its provenance rows; assert counts and that `recorded_at` is set).
- [ ] Run → **FAIL**.
- [ ] Implement `derive_content_key` (lowercase+strip label, join with `\x1f`, `hashlib.sha256().hexdigest()`). Implement `insert_object`: `id=uuid4().hex`, default `recorded_at=datetime.now(UTC).isoformat()`, `content_key=content_key or derive_content_key(...)`, `INSERT` object then loop `INSERT` provenance rows (`object_table='knowledge_objects'`), single `await db.commit()`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): persist knowledge objects with provenance rows`.

---

### Task 7 — L1 store: relationship write + object lookups

**Files:** `archivum/graph/store.py`, `tests/graph/test_store.py`

**Interfaces (candidate write API, part 2):**
- Produces `async def insert_relationship(rel: CandidateRelationship, ref_to_id: dict[str, str]) -> str` (resolves `from_ref`/`to_ref` through `ref_to_id`; writes relationship + provenance).
- Produces `async def get_object(id: str) -> dict | None`, `async def find_objects_by_content_key(content_key: str, scope: str) -> list[dict]`, `async def list_objects(kind: str | None = None, scope: str | None = None) -> list[dict]`.

- [ ] Write **failing** tests: `test_insert_relationship_resolves_refs` (insert two objects, map refs→ids, insert rel, read back `from_id`/`to_id`), `test_find_objects_by_content_key`, `test_insert_relationship_unknown_ref_raises KeyError`.
- [ ] Run → **FAIL**.
- [ ] Implement the three lookups + `insert_relationship` (`from_id=ref_to_id[rel.from_ref]`; on missing key raise `KeyError` — validation already guarantees presence in the happy path). Provenance rows tagged `object_table='relationships'`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): persist relationships and add object lookup queries`.

---

### Task 8 — Entity resolution / dedup

**Files:** `archivum/graph/resolution.py`, `tests/graph/test_resolution.py`

**Interfaces:**
- Produces `async def resolve_object(obj: CandidateObject) -> ResolutionResult` where `@dataclass ResolutionResult(existing_id: str | None, content_key: str, merged_attrs: dict)`.
- Policy: exact `content_key` match within same `scope` → reuse `existing_id`, merge `attrs` (union; existing wins on conflict), keep higher confidence. No fuzzy matching in v1 (deterministic, testable).
- Produces `async def upsert_object(obj: CandidateObject) -> str` → resolve, then either `insert_object` (new) or attach fresh provenance to the existing id via `async def add_provenance(object_id, object_table, evidence)`.

- [ ] Write **failing** tests: `test_resolve_new_object_no_existing`, `test_resolve_matches_existing_by_content_key_and_scope`, `test_different_scope_not_merged`, `test_upsert_existing_adds_provenance_not_duplicate_row` (insert same entity from two chunks → one `knowledge_objects` row, two `provenance` rows).
- [ ] Run → **FAIL**.
- [ ] Implement `add_provenance` in `store.py` (append-only). Implement `resolve_object` using `find_objects_by_content_key`. Implement `upsert_object`: if match, `add_provenance` + bump confidence when higher; else `insert_object`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): deterministic entity resolution and dedup upsert`.

---

### Task 9 — Contradiction detection + supersession edges

**Files:** `archivum/graph/contradiction.py`, `tests/graph/test_contradiction.py`

**Interfaces:**
- Produces `async def detect_contradiction(claim: CandidateObject, existing: list[dict]) -> list[str]` → returns ids of existing claims contradicted by the new one.
- Policy (v1, deterministic): two `claim`-kind objects contradict when same `scope` + same `attrs["subject"]` + same `attrs["predicate"]` + **different** `attrs["object"]` with overlapping validity intervals.
- Produces `async def record_supersession(superseded_id, superseding_id, reason)` → inserts a `supersession` row (both rows survive in `knowledge_objects`; §4/invariant 4).
- Produces `async def apply_supersession(new_id: str, contradicted_ids: list[str])` → records supersession for each and closes out the superseded claim's `valid_to` to the new claim's `valid_from` (bitemporal close-out) **without deleting** it.

- [ ] Write **failing** tests: `test_detect_contradiction_same_subject_diff_object`, `test_no_contradiction_when_object_matches`, `test_no_contradiction_disjoint_validity`, `test_record_supersession_keeps_both_rows`, `test_apply_supersession_closes_valid_to`.
- [ ] Run → **FAIL**.
- [ ] Implement using `temporal.intervals_overlap` (Task 10 — **reorder if needed: do Task 10 first**; this plan lists Task 10 next and Task 9's overlap check imports it, so implement Task 10's `intervals_overlap` before this step or inline a tiny local helper and replace it in Task 10). Implement detection, `record_supersession`, `apply_supersession` (UPDATE only `valid_to`, never DELETE).
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): contradiction detection with supersession edges`.

---

### Task 10 — Bitemporal helpers

**Files:** `archivum/graph/temporal.py`, `tests/graph/test_temporal.py`

**Interfaces:**
- Produces `def intervals_overlap(a_from, a_to, b_from, b_to) -> bool` (None = open bound), `def now_iso() -> str`, `def close_interval(valid_to_target: str, current_to: str | None) -> str` (returns earliest of the two, treating None as open/infinite).

- [ ] Write **failing** tests: `test_overlap_open_bounds`, `test_overlap_disjoint`, `test_close_interval_picks_earliest`.
- [ ] Run → **FAIL**.
- [ ] Implement `temporal.py` with ISO-8601 string comparison (lexicographic works for `isoformat` UTC). Replace any inline overlap helper from Task 9 with an import of `intervals_overlap`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): bitemporal interval helpers`.

---

### Task 11 — Work queue

**Files:** `archivum/graph/queue.py`, `tests/graph/test_queue.py`; schema addition in `archivum/graph/schema.py`

**Interfaces (mirrors existing `page_write_jobs` claim pattern in `db/sqlite.py`):**
- Table `graph_work_queue(id INTEGER PK, document_id TEXT, source_id TEXT, scope TEXT, status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, content_hash TEXT, error TEXT, created_at, started_at, finished_at)`.
- Produces `async def enqueue_document(document_id, source_id, scope, content_hash) -> int`, `async def claim_next_job() -> dict | None` (atomic `BEGIN IMMEDIATE` → set `processing`), `async def complete_job(job_id)`, `async def fail_job(job_id, error)` (increments `attempts`).

- [ ] Add `graph_work_queue` DDL to `KNOWLEDGE_SCHEMA` in Task 2's file (extend `init_knowledge_schema`); this is fine because migration is idempotent.
- [ ] Write **failing** tests: `test_enqueue_then_claim_marks_processing`, `test_claim_returns_none_when_empty`, `test_complete_and_fail_transitions`, `test_fail_increments_attempts`.
- [ ] Run → **FAIL**.
- [ ] Implement `queue.py` copying the `claim_next_page_write_job` transaction pattern.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): document work queue with atomic claim`.

---

### Task 12 — Deterministic MockWorker (for tests)

**Files:** `archivum/graph/mock_worker.py`, `tests/graph/test_mock_worker.py`

**Interfaces:**
- Produces `class MockWorker` implementing the worker contract: `async def extract(self, document: dict, chunks: list[dict]) -> CandidateBatch`.
- Deterministic: given a document whose text contains `"NAME: X"` lines, emits one `ENTITY` candidate per name with `EXTRACTED` method, confidence `0.9`, evidence pointing at the containing chunk span, scope from the document. Emits a `RELATED_TO` relationship between consecutive names. No LLM, no randomness — fully reproducible for pipeline tests.

- [ ] Write **failing** tests: `test_mock_worker_extracts_named_entities` (two `NAME:` lines → two entities + one relationship, each with valid evidence spans that resolve), `test_mock_worker_is_deterministic` (same input twice → equal batches).
- [ ] Run → **FAIL**.
- [ ] Implement `MockWorker.extract`: scan chunks for `NAME:` prefixed lines, compute span offsets within the chunk, build `CandidateObject`/`CandidateRelationship`/`CandidateBatch`.
- [ ] Run → **PASS**.
- [ ] Commit: `test(graph): deterministic mock extraction worker`.

---

### Task 13 — PTY worker harness + skill contract

**Files:** `archivum/graph/worker.py`, `tests/graph/test_worker.py`

**Interfaces:**
- Produces `class WorkerProtocol(Protocol)` with `async def extract(document, chunks) -> CandidateBatch`.
- Produces `@dataclass WorkerSpec(command: list[str], skill_dir: str, timeout_s: float)` describing a PTY-hosted worker + its indexing/sorting skill directory.
- Produces `class PtyWorkerHarness` with `async def run(self, spec, document, chunks) -> CandidateBatch`: spawns the command under a PTY (`pty.openpty` + `asyncio` subprocess), writes a JSON job envelope (`{"document":..,"chunks":..,"skill_dir":..}`) to stdin, reads a JSON `CandidateBatch` envelope from stdout, parses via `parse_candidate_batch(json)`.
- Produces `def parse_candidate_batch(payload: dict, source_id, document_id) -> CandidateBatch` (shared JSON→dataclass parser; also used by `mock_worker` serialization tests).
- Produces `on_session_captured: Callable[[dict], Awaitable[None]]` hook (default no-op) — PER-316 integration point: the harness's captured PTY transcript is handed to this callback so the agent session becomes a Source.

- [ ] Write **failing** tests: `test_parse_candidate_batch_roundtrip` (serialize a MockWorker batch to JSON, parse back, assert equality), `test_pty_harness_runs_echo_script` (use a tiny inline python `-c` script that reads the envelope and echoes a fixed batch; assert parsed batch matches), `test_on_session_captured_hook_invoked` (monkeypatch hook, assert it received the transcript dict).
- [ ] Run → **FAIL**.
- [ ] Implement `parse_candidate_batch`, `WorkerProtocol`, `WorkerSpec`, `PtyWorkerHarness.run` (PTY spawn, envelope write, timeout via `asyncio.wait_for`, transcript capture → `await on_session_captured(...)`).
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): PTY worker harness with skill/session-capture contract`.

---

### Task 14 — Extraction pipeline (queue → worker → validate → write)

**Files:** `archivum/graph/pipeline.py`, `tests/graph/test_pipeline.py`

**Interfaces (the end-to-end write path; this is what `--update` and ingestion call):**
- Produces `async def process_job(job: dict, worker: WorkerProtocol) -> ProcessResult` and `@dataclass ProcessResult(objects_written: int, relationships_written: int, superseded: int, rejected: int)`.
- Flow: load `documents`/`chunks` for `job["document_id"]` → `worker.extract(...)` → `ValidationLayer.validate_batch(...)` (reject-and-count on `ValidationError`, do not abort whole batch) → for each valid object `upsert_object` building `ref_to_id` map → for `claim` kinds run `detect_contradiction` against existing + `apply_supersession` → `insert_relationship` for each rel.
- Produces `async def run_worker_loop(worker, max_jobs=None)` → `claim_next_job` loop calling `process_job`, `complete_job`/`fail_job`.

- [ ] Write **failing** tests using `MockWorker`: `test_process_job_writes_objects_and_relationships` (seed doc with two `NAME:` lines, enqueue, `process_job` → 2 objects, 1 rel in L1), `test_process_job_rejects_invalid_candidate` (worker emitting confidence 2.0 → counted in `rejected`, not written), `test_process_job_supersedes_contradicting_claim`, `test_run_worker_loop_drains_queue`.
- [ ] Run → **FAIL**.
- [ ] Implement `pipeline.py` wiring all prior modules. Build `ref_to_id` from `content_key`→returned id as objects are upserted.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): end-to-end extraction pipeline with validation and supersession`.

---

### Task 15 — Caching (content-hash + prompt-fingerprint)

**Files:** `archivum/graph/cache.py`, `tests/graph/test_cache.py`; schema addition in `schema.py`

**Interfaces:**
- Tables `extraction_cache(content_hash TEXT, extractor_version TEXT, result_json TEXT, created_at, PRIMARY KEY(content_hash, extractor_version))` and `prompt_fingerprint_cache(fingerprint TEXT PRIMARY KEY, result_json TEXT, created_at)`.
- Produces `def content_hash_key(document_content: str, extractor_version: str) -> str`, `def prompt_fingerprint(prompt: str) -> str` (sha256 of normalized prompt; version-independent).
- Produces `async def get_cached_by_content(content_hash, extractor_version) -> CandidateBatch | None`, `async def put_cached_by_content(...)`, `async def get_cached_by_fingerprint(fingerprint) -> CandidateBatch | None`, `async def put_cached_by_fingerprint(...)`.
- `process_job` (Task 14) is extended: before calling the worker, check `get_cached_by_content`; if hit, skip the worker entirely. After a fresh extraction, `put_cached_by_content` and `put_cached_by_fingerprint`.

- [ ] Add the two tables to `KNOWLEDGE_SCHEMA`.
- [ ] Write **failing** tests: `test_content_cache_hit_skips_worker` (spy worker whose `extract` raises if called; pre-seed cache → `process_job` succeeds without calling worker), `test_prompt_fingerprint_survives_version_bump` (fingerprint identical across two `extractor_version` values), `test_cache_roundtrip_batch`.
- [ ] Run → **FAIL**.
- [ ] Implement `cache.py` (JSON via the Task-13 serializer). Wire the content-hash check into `process_job` (guarded so existing Task-14 tests still pass — cache miss path unchanged).
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): content-hash and prompt-fingerprint extraction caches`.

---

### Task 16 — Kuzu projector (L1 → graph index)

**Files:** `archivum/graph/projectors.py`, `tests/graph/test_projectors.py`

**Interfaces:**
- Produces `async def rebuild_kuzu_from_l1() -> dict[str, int]` → drops PER-317 node/rel tables and re-creates + re-populates from `knowledge_objects` + `relationships`. Returns `{"nodes":n,"rels":m}`.
- Uses `archivum.db.graph._get_conn` / `_run`. Adds Kuzu tables `KObject(id, kind, scope, label)` and `KREL(FROM KObject TO KObject, rel_type, confidence)`.

- [ ] Write **failing** test `test_rebuild_kuzu_projects_objects_and_edges`: seed L1 (via pipeline+MockWorker) with 2 objects + 1 rel, call `rebuild_kuzu_from_l1`, then query Kuzu for `MATCH (a:KObject)-[r:KREL]->(b:KObject) RETURN count(*)` == 1 and node count == 2.
- [ ] Run → **FAIL**.
- [ ] Implement: DDL create-if-not-exists for `KObject`/`KREL`; `DELETE` all existing PER-317 nodes (`MATCH (n:KObject) DETACH DELETE n`); `SELECT` L1 objects → `CREATE`/`MERGE` nodes; `SELECT` relationships → `MATCH ... MERGE` edges. Wrap sync Kuzu in `_run`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): Kuzu projector rebuilding graph index from L1`.

---

### Task 17 — Qdrant + FTS projectors (L1 → vector/keyword indexes)

**Files:** `archivum/graph/projectors.py`, `tests/graph/test_projectors.py`; FTS DDL in `schema.py`

**Interfaces:**
- Produces `async def rebuild_qdrant_from_l1() -> dict[str,int]`: embeds each object's `label`+`attrs` text via `qdrant_client.embed_texts`, upserts into a `knowledge_objects` Qdrant collection keyed by object id; clears the collection first.
- Produces `async def rebuild_fts_from_l1() -> dict[str,int]`: rebuilds an FTS5 table `knowledge_fts(id UNINDEXED, label, body)` from L1 (drop + repopulate).
- Add `knowledge_fts` virtual table DDL to `schema.py` (created empty; projector populates).

- [ ] Write **failing** tests: `test_rebuild_fts_indexes_objects` (seed 2 objects, rebuild, `MATCH` a label token → 1 hit), `test_rebuild_qdrant_indexes_objects` (use in-memory Qdrant from fixture; after rebuild, `count` points == object count). Skip Qdrant embedding network by using local `embed_provider` in test Settings.
- [ ] Run → **FAIL**.
- [ ] Implement both projectors. FTS: `DELETE FROM knowledge_fts` then `INSERT`. Qdrant: `delete_collection`+`init` then `embed_texts` + `upsert` (reuse patterns from `qdrant_client.upsert_page`).
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): Qdrant and FTS projectors from L1`.

---

### Task 18 — `rebuild_indexes()` orchestrator (drop-and-rebuild command)

**Files:** `archivum/graph/projectors.py`, `tests/graph/test_rebuild.py`

**Interfaces (the single command PER-319 relies on; invariant 2 / spec §6.6):**
- Produces `async def rebuild_indexes(targets: set[str] | None = None) -> dict[str, dict]` → runs `rebuild_kuzu_from_l1`, `rebuild_qdrant_from_l1`, `rebuild_fts_from_l1` (all by default; subset via `targets ⊆ {"kuzu","qdrant","fts"}`). Returns per-target counts. Idempotent: running twice yields identical index state.

- [ ] Write **failing** tests: `test_rebuild_indexes_runs_all_targets`, `test_rebuild_indexes_is_idempotent` (run twice → identical counts, no duplicate Kuzu edges/FTS rows), `test_rebuild_indexes_subset_target` (`targets={"fts"}` touches only FTS).
- [ ] Run → **FAIL**.
- [ ] Implement `rebuild_indexes` dispatching to the three projectors.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): rebuild_indexes orchestrator (drop-and-rebuild)`.

---

### Task 19 — `--update` incremental re-extraction + dangling-edge pruning

**Files:** `archivum/graph/update.py`, `tests/graph/test_update.py`

**Interfaces:**
- Produces `async def update_changed_sources(worker: WorkerProtocol) -> UpdateResult` and `@dataclass UpdateResult(reextracted, skipped_by_cache, pruned_objects, pruned_edges)`.
- Flow: for each `document`, compute `content_hash_key`; if unchanged vs `extraction_cache` → skip (count `skipped_by_cache`); else enqueue + `process_job`. After processing: `async def prune_dangling() -> tuple[int,int]` deletes `provenance` rows whose `chunk_id` no longer exists, then deletes `knowledge_objects` with zero remaining provenance (invariant 3 — an object with no evidence cannot exist), then deletes `relationships` whose `from_id`/`to_id` no longer exist. Pruned supersession rows for deleted claims are removed too. Finally calls `rebuild_indexes()` so L2 reflects L1.

- [ ] Write **failing** tests: `test_update_skips_unchanged_via_cache`, `test_update_reextracts_changed_document`, `test_prune_removes_objects_with_no_provenance` (delete a chunk row, run prune → its evidence-only object gone), `test_prune_removes_dangling_relationships`, `test_update_rebuilds_indexes`.
- [ ] Run → **FAIL**.
- [ ] Implement `update.py` reusing `pipeline.process_job`, `cache`, `projectors.rebuild_indexes`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): incremental --update with dangling-edge pruning`.

---

### Task 20 — CLI entrypoints

**Files:** `archivum/graph/cli.py`, `tests/graph/test_cli.py`; register in `archivum/__main__.py`

**Interfaces:**
- Produces `async def cmd_rebuild_indexes(argv) -> int` (`graph rebuild-indexes [--targets kuzu,qdrant,fts]`) and `async def cmd_update(argv) -> int` (`graph update`), both returning a process exit code and printing a JSON summary.
- Wire into `archivum/__main__.py` under a `graph` subcommand group without disturbing existing commands.

- [ ] Write **failing** tests: `test_cli_rebuild_indexes_returns_zero_and_prints_summary` (capture stdout, assert JSON has the three targets), `test_cli_update_returns_zero`.
- [ ] Run → **FAIL**.
- [ ] Implement `cli.py` (thin argparse over `rebuild_indexes`/`update_changed_sources` using a `MockWorker` when no real worker configured), register the subcommand in `__main__.py`.
- [ ] Run → **PASS**.
- [ ] Commit: `feat(graph): CLI for rebuild-indexes and incremental update`.

---

### Task 21 — Full-suite verification & wiring check

**Files:** none (verification only)

- [ ] Run `pytest tests/graph -q` → expect **all PASS**.
- [ ] Run `python -c "import archivum.graph.pipeline, archivum.graph.projectors, archivum.graph.update, archivum.graph.cli"` → no import errors.
- [ ] Grep the package for `TODO`, `pass  # `, `NotImplemented`, `...` bodies → expect **none**.
- [ ] Confirm `rebuild_indexes` and the candidate write API (`ValidationLayer`, `CandidateBatch`, `upsert_object`, `insert_relationship`) are importable from `archivum.graph` for PER-318/PER-319 (add re-exports to `archivum/graph/__init__.py`).
- [ ] Commit: `chore(graph): re-export public write/rebuild API for downstream epics`.

---

## Self-Review

- **Spec coverage:** L1 schema + provenance/confidence/temporal/scope/supersession (T2, T3); validation layer invariants §4/§6 (T5); agent-worker queue (T11) + PTY harness/skill contract (T13) + deterministic mock (T12); candidate ingestion/write path (T6–T7, T14); entity resolution/dedup (T8); contradiction + supersedes/superseded_by (T9); bitemporal (T10, close-out in T9/T19); index projectors rebuilding Kuzu+Qdrant+FTS from L1 + drop-and-rebuild (T16–T18); caching AST content-hash + semantic prompt-fingerprint (T15); `--update` incremental + dangling-edge pruning (T19). All spec §5 items covered.
- **Placeholder scan:** no step defers implementation; Task 21 enforces a grep gate. Task 9↔10 ordering note added inline (implement `intervals_overlap` before Task 9's overlap step).
- **Type consistency:** every referenced type is defined — `ExtractionMethod`/`ObjectKind`/`EvidenceSpan`/`CandidateObject`/`CandidateRelationship`/`CandidateBatch` (T3); `ResolvedEvidence`/`DanglingEvidenceError` (T4); `ValidationError`/`ValidationLayer` (T5); `ResolutionResult` (T8); `ProcessResult` (T14); `WorkerProtocol`/`WorkerSpec`/`PtyWorkerHarness`/`parse_candidate_batch` (T13); `UpdateResult` (T19). Upstream `sources`/`documents`/`chunks` shape flagged as a PER-315 assumption with a single point of change (Task 1 fixture).
- **Downstream contract:** candidate write API (`ValidationLayer.validate_batch` + `upsert_object`/`insert_relationship`) and `rebuild_indexes()` re-exported in Task 21 for PER-318/PER-319.
