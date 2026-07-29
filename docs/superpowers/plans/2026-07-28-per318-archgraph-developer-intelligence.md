# PER-318: Archgraph — Cross-Repository Developer Intelligence — Implementation Plan

**For agentic workers:** Execute tasks in order. Each task is TDD: write a real pytest test, run it, watch it FAIL, write the minimal real implementation, run it, watch it PASS, commit. Steps are sized 2–5 minutes. No placeholders — every code block is real, runnable code with real tree-sitter usage and real fixtures. All types are defined before use. Do not skip the FAIL run; a test that passes before implementation is a broken test. When a step says "commit", use a semantic commit message (`feat:`, `test:`, `fix:`).

---

## Goal

Build **Archgraph** — the code-typed slice of Archivum's unified L1 graph (spec §7). A **deterministic** tree-sitter AST extractor (multi-language, starting with Python + TypeScript, structured to add more) runs in the deterministic ingestion stage with **zero LLM cost**. It emits code-typed L1 objects: `Entity` (symbol/module/type/package), `Artifact` (file/repo/commit/PR/test/deployment), `Relationship` (calls/imports/inherits/depends_on/references), each stamped with `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`. A cross-repository resolver links the same symbol/package across repos and commits. Evidence bridging connects code symbols to the conversation/PR/deploy/incident evidence already in L1 (from PER-316/317). Code retrieval uses graph traversal + lexical (trigram/IDF) scoring — **no vectors**.

## Architecture

Archgraph is **not a separate store**. It is a producer for the deterministic stage (spec §5) that writes code-typed candidate objects through PER-317's validation layer into the L1 SQLite store of record. The pipeline mirrors graphify's stage separation but lands in L1 instead of NetworkX:

```
repo path ──▶ collect_files ──▶ per-file AST extract (tree-sitter) ──▶ {nodes, edges} dicts
                                            │ (AST cache, content-hash keyed)
                                            ▼
              cross-file symbol resolution (INFERRED calls/references)
                                            ▼
              map nodes/edges ──▶ PER-317 candidate objects (Entity/Artifact/Relationship)
                                            ▼
              PER-317 validation layer ──▶ L1 SQLite (store of record)
                                            ▼
              cross-repo resolver (entity resolution across repos+commits, INFERRED)
                                            ▼
              evidence bridging (link code symbols ↔ conversation/PR/deploy evidence)
                                            ▼
              rebuild_indexes() ──▶ L2 (Kuzu graph + code lexical/trigram index)
                                            ▼
              code retrieval: seed ──▶ BFS neighborhood ──▶ lexical score ──▶ scoped subgraph
```

Everything below L1 is rebuildable. Code retrieval reads L2 (graph + trigram/IDF), never Qdrant.

## Tech Stack

- **Python 3.12+**, matching `apps/backend/archivum/` conventions (aiosqlite, FastAPI, pydantic-settings).
- **tree-sitter** (`tree-sitter>=0.23`) — the parsing runtime.
- **Language grammars** (PyPI wheels, no compilation): `tree-sitter-python>=0.23`, `tree-sitter-typescript>=0.23` (ships `language_typescript` for `.ts`/`.mts`/`.cts` and `language_tsx` for `.tsx`). Structured so adding `tree-sitter-go`, `tree-sitter-java`, `tree-sitter-rust`, etc. is one registry entry + one config each.
- **L1:** existing SQLite store of record (`archivum/db/sqlite.py`), extended with Entity/Artifact/Relationship tables via PER-317 (see Upstream Dependencies).
- **L2:** existing Kuzu (`archivum/db/graph.py`) for traversal; a new SQLite-backed trigram/IDF index for code lexical retrieval (no Qdrant for code).
- **pytest** (`pytest>=9`, `pytest-asyncio`, `asyncio_mode=auto` per `pytest.ini`), run from repo root: `pytest tests/archgraph/ -q`.

## Global Constraints

From spec §5, §6, §7 — these are invariants, not preferences:

1. **Code extraction is deterministic and zero-LLM.** No LLM call may touch code at any point in this subsystem. The extractor is reproducible: same bytes in ⇒ same nodes/edges out.
2. **Same L0–L3 layering.** Archgraph adds no new store. Code objects are ordinary L1 knowledge objects (Entity/Artifact/Relationship) written through PER-317's validation layer. L2 indexes and L3 views are rebuildable from L1.
3. **Code uses graph + lexical retrieval, never vectors.** Qdrant is for natural-language sources only. Code retrieval = deterministic graph traversal (BFS) + trigram/IDF lexical scoring.
4. **Every edge carries an extraction method.** Every emitted `Relationship` has `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`: `EXTRACTED` = directly stated in source (import statement, direct call); `INFERRED` = cross-file/cross-repo resolution; `AMBIGUOUS` = conflicting/low-confidence, flagged for review.
5. **Every L1 object carries ≥1 provenance link, a confidence score, and an extraction method** (spec §4 invariant). Code nodes anchor provenance to a `Chunk` spanning the file/symbol's source line range.

---

## File Structure

```
apps/backend/archivum/archgraph/
    __init__.py            # public API re-exports
    registry.py            # LanguageConfig dataclass + LANGUAGE_REGISTRY + dispatch by suffix
    extractors/
        __init__.py
        base.py            # _make_id, _file_stem, _read_text, _source_location helpers
        python_ext.py      # extract_python (tree-sitter-python)
        typescript_ext.py  # extract_typescript (tree-sitter-typescript, ts/tsx)
    extract.py             # extract_file(path) dispatch → {nodes, edges} + _extract_generic
    resolve.py             # resolve_cross_file(extractions) → INFERRED calls/references edges
    mapper.py              # code dicts → PER-317 candidate Entity/Artifact/Relationship objects
    cache.py               # content-hash AST cache (load_cached/save_cached), version-namespaced
    repo.py                # RepoSnapshot: repo/commit Artifacts, git metadata, file walk
    cross_repo.py          # resolve_cross_repo(): link same symbol/package across repos+commits
    bridge.py              # bridge_evidence(): link code symbols ↔ PR/conversation/deploy L1 evidence
    lexical.py             # trigram + IDF index over code nodes (SQLite-backed, L2)
    retrieval.py           # retrieve_code(query) → seed → BFS neighborhood → lexical score → subgraph
    ingest.py              # ingest_repo(path): full deterministic pipeline entrypoint + incremental --update
    hook.py                # git-hook / CLI entrypoint (archivum-archgraph ingest <repo>)
    models.py              # CodeNode, CodeEdge, ExtractionMethod, CandidateEntity/Artifact/Relationship dataclasses

tests/archgraph/
    __init__.py
    conftest.py            # tmp repo fixture, sample-code fixtures
    fixtures/
        py_sample/         # small multi-file Python package
        ts_sample/         # small multi-file TypeScript project
    test_registry.py
    test_extract_python.py
    test_extract_typescript.py
    test_resolve.py
    test_mapper.py
    test_cache.py
    test_repo.py
    test_cross_repo.py
    test_bridge.py
    test_lexical.py
    test_retrieval.py
    test_ingest.py
    test_hook.py
    test_end_to_end.py
```

---

## Upstream Dependencies

**PER-317 (Provenance-Aware Graph Construction)** — dependency. This plan plugs into PER-317's:

- **Entity / Artifact / Relationship tables** in L1 SQLite (spec §4). Assumed columns per object: `id TEXT PK`, `kind TEXT` (e.g. `symbol`/`module`/`type`/`package` for Entity; `file`/`repo`/`commit`/`pr`/`test`/`deployment` for Artifact), `name TEXT`, `scope TEXT`, `confidence REAL`, `extraction_method TEXT`, plus provenance rows in a `provenance(object_id, chunk_id, span, extraction_method)` table. Relationship adds `src_id`, `dst_id`, `rel_type`.
- **Validation layer** — a single write API that accepts candidate objects, enforces the §4 invariant (≥1 provenance link, confidence, extraction_method, valid scope), and lands them in L1. Assumed signature:
  ```python
  # archivum/graph/validation.py (owned by PER-317)
  async def write_candidates(conn, candidates: list[Candidate]) -> WriteResult: ...
  # Candidate is a tagged union: CandidateEntity | CandidateArtifact | CandidateRelationship
  # WriteResult carries .written_ids: list[str] and .rejected: list[tuple[Candidate, str]]
  ```
- **`rebuild_indexes(conn)`** — drops and rebuilds L2 (Kuzu + FTS) from L1 edges.
- **Chunk write API** — to anchor code provenance to a `Chunk` (document span).

**ASSUMPTION (PER-317 plan file absent at authoring time):** The PER-317 plan
`docs/superpowers/plans/2026-07-28-per317-provenance-aware-graph-construction.md` was
**not present** when this plan was written. The interfaces above are derived from spec §4/§5.
**Task 5 defines a thin adapter (`archgraph/mapper.py`) against these assumed signatures**, isolating
Archgraph from PER-317's exact API. If PER-317's real signatures differ, only `mapper.py` and its
test change — every other task consumes `mapper.py`, not PER-317 directly. Before starting Task 5,
grep for the real API (`rg "def write_candidates|class Candidate|def rebuild_indexes" apps/backend`)
and reconcile the adapter; if absent, implement the adapter against a local in-memory fake
(`tests/archgraph/conftest.py::FakeValidationLayer`) so Archgraph tests run standalone.

---

### Task 1 — Package scaffold + core dataclasses (`models.py`)

**Files:** `apps/backend/archivum/archgraph/__init__.py`, `apps/backend/archivum/archgraph/models.py`, `tests/archgraph/__init__.py`, `tests/archgraph/test_models.py`

**Interfaces:**
- **Produces:**
  ```python
  # archgraph/models.py
  from __future__ import annotations
  from dataclasses import dataclass, field
  from enum import Enum

  class ExtractionMethod(str, Enum):
      EXTRACTED = "EXTRACTED"
      INFERRED = "INFERRED"
      AMBIGUOUS = "AMBIGUOUS"

  @dataclass(frozen=True)
  class CodeNode:
      id: str
      label: str
      kind: str            # symbol|module|type|package|file
      source_file: str
      source_location: str # "L42" or "L42-L88"

  @dataclass(frozen=True)
  class CodeEdge:
      source: str
      target: str
      relation: str        # calls|imports|inherits|depends_on|references
      method: ExtractionMethod
      source_file: str
      source_location: str
      confidence: float = 1.0

  @dataclass(frozen=True)
  class Extraction:
      nodes: list[CodeNode]
      edges: list[CodeEdge]
      error: str | None = None
  ```

- [ ] Create `tests/archgraph/__init__.py` (empty) and `apps/backend/archivum/archgraph/__init__.py` (empty for now).
- [ ] Write `tests/archgraph/test_models.py::test_extraction_method_values` asserting `ExtractionMethod.EXTRACTED.value == "EXTRACTED"` and that the enum has exactly the 3 members.
- [ ] Write `test_models.py::test_codeedge_defaults` asserting `CodeEdge(..., method=ExtractionMethod.EXTRACTED, ...).confidence == 1.0` and that `CodeNode`/`CodeEdge`/`Extraction` are hashable (frozen).
- [ ] Run `pytest tests/archgraph/test_models.py -q` → FAIL (ImportError, no `models.py`).
- [ ] Implement `archgraph/models.py` with the dataclasses above.
- [ ] Run `pytest tests/archgraph/test_models.py -q` → PASS.
- [ ] Commit: `feat(archgraph): core code node/edge dataclasses and extraction method enum`.

---

### Task 2 — Language registry + dispatch (`registry.py`, `extractors/base.py`)

**Files:** `apps/backend/archivum/archgraph/registry.py`, `apps/backend/archivum/archgraph/extractors/__init__.py`, `apps/backend/archivum/archgraph/extractors/base.py`, `tests/archgraph/test_registry.py`

**Interfaces:**
- **Consumes:** `tree_sitter.Language`, `tree_sitter.Parser`.
- **Produces:**
  ```python
  # archgraph/registry.py
  from dataclasses import dataclass, field
  from tree_sitter import Language, Parser

  @dataclass(frozen=True)
  class LanguageConfig:
      name: str
      suffixes: tuple[str, ...]
      ts_module: str                 # e.g. "tree_sitter_python"
      ts_language_fn: str = "language"  # attr on the module returning the grammar
      class_types: frozenset[str] = frozenset()
      function_types: frozenset[str] = frozenset()
      import_types: frozenset[str] = frozenset()
      call_types: frozenset[str] = frozenset()

  def load_parser(cfg: LanguageConfig) -> Parser: ...   # importlib the ts_module, build Parser
  def config_for_suffix(suffix: str) -> LanguageConfig | None: ...
  LANGUAGE_REGISTRY: dict[str, LanguageConfig]          # suffix -> config
  CODE_SUFFIXES: frozenset[str]
  ```
  ```python
  # archgraph/extractors/base.py
  def _make_id(*parts: str) -> str: ...       # slug: lower, non-alnum -> "_", join with "_"
  def _file_stem(path: Path) -> str: ...      # parent_dir_stem, no extension (graphify semantics)
  def _read_text(node, source: bytes) -> str: ...
  def _source_location(node) -> str: ...      # "L{start+1}-L{end+1}"
  ```

- [ ] Add `tree-sitter>=0.23`, `tree-sitter-python>=0.23`, `tree-sitter-typescript>=0.23` to `apps/backend/pyproject.toml` `[project].dependencies`; run `uv sync` (or `pip install -e .`) in `apps/backend`.
- [ ] Write `test_registry.py::test_python_suffix_maps` asserting `config_for_suffix(".py").name == "python"` and `".ts" in LANGUAGE_REGISTRY` and `config_for_suffix(".rb") is None`.
- [ ] Write `test_registry.py::test_load_parser_parses` — load the Python config, `parser.parse(b"x = 1")`, assert `tree.root_node.type == "module"` and no `has_error`.
- [ ] Write `test_registry.py::test_make_id_slugifies` asserting `_make_id("Foo/Bar", "baz.py") == "foo_bar_baz_py"` (define exact expected form to match `_source_location`/id conventions).
- [ ] Run `pytest tests/archgraph/test_registry.py -q` → FAIL.
- [ ] Implement `extractors/base.py` helpers (mirror graphify `_make_id`/`_read_text`/`_file_stem` semantics; `_source_location` returns `f"L{n.start_point[0]+1}-L{n.end_point[0]+1}"`).
- [ ] Implement `registry.py`: `_PYTHON_CONFIG` and `_TS_CONFIG`/`_TSX_CONFIG` (suffixes `.ts/.mts/.cts` vs `.tsx`, `ts_language_fn="language_typescript"`/`"language_tsx"`), `LANGUAGE_REGISTRY` built from them, `load_parser` via `importlib.import_module(cfg.ts_module)` + `getattr(mod, cfg.ts_language_fn)()`.
- [ ] Run `pytest tests/archgraph/test_registry.py -q` → PASS.
- [ ] Commit: `feat(archgraph): tree-sitter language registry with python+typescript configs`.

---

### Task 3 — Python AST extractor (`extractors/python_ext.py`, `extract.py`)

**Files:** `apps/backend/archivum/archgraph/extract.py`, `apps/backend/archivum/archgraph/extractors/python_ext.py`, `tests/archgraph/fixtures/py_sample/`, `tests/archgraph/test_extract_python.py`

**Interfaces:**
- **Consumes:** `LanguageConfig`, `load_parser`, base helpers, `CodeNode`/`CodeEdge`/`Extraction`.
- **Produces:**
  ```python
  # archgraph/extract.py
  def extract_file(path: Path) -> Extraction: ...   # dispatch by suffix via registry
  def _extract_generic(path: Path, cfg: LanguageConfig) -> Extraction: ...
  ```
  ```python
  # archgraph/extractors/python_ext.py
  def extract_python(path: Path) -> Extraction: ...
  ```

- [ ] Create fixture `tests/archgraph/fixtures/py_sample/calc.py`:
  ```python
  """Calculator module."""
  import math

  class Calculator:
      def add(self, a, b):
          return a + b

      def hypot(self, a, b):
          return math.sqrt(self.add(a * a, b * b))
  ```
- [ ] Write `test_extract_python.py::test_extracts_class_and_methods` — `extract_file(calc)` yields a `type`-kind node `Calculator`, `symbol`-kind nodes for `add`/`hypot`, and a `file`-kind node; assert ids via `_make_id`.
- [ ] Write `test_extract_python.py::test_extracts_import_edge` asserting an `imports` edge to `math` with `method == ExtractionMethod.EXTRACTED`.
- [ ] Write `test_extract_python.py::test_extracts_intrafile_call` asserting a `calls` edge `hypot -> add` and a `references`/`calls` edge to `math.sqrt` (external → still EXTRACTED at the call site).
- [ ] Run `pytest tests/archgraph/test_extract_python.py -q` → FAIL.
- [ ] Implement `_extract_generic`: parse via `load_parser(cfg)`, walk for `class_types`→`type` nodes, `function_types`→`symbol` nodes (id = `_make_id(stem, class, func)`), `import_types`→`imports` edges (EXTRACTED), `call_types`→`calls` edges (EXTRACTED) resolving the callee name within the enclosing function body. Emit one `file` node. Guard exceptions → `Extraction(nodes=[], edges=[], error=...)`.
- [ ] Implement `extract_python` = `_extract_generic(path, _PYTHON_CONFIG)`; wire `extract_file` dispatch through `config_for_suffix`.
- [ ] Run `pytest tests/archgraph/test_extract_python.py -q` → PASS.
- [ ] Commit: `feat(archgraph): deterministic python AST extractor (classes, imports, calls)`.

---

### Task 4 — TypeScript AST extractor (`extractors/typescript_ext.py`)

**Files:** `apps/backend/archivum/archgraph/extractors/typescript_ext.py`, `tests/archgraph/fixtures/ts_sample/`, `tests/archgraph/test_extract_typescript.py`

**Interfaces:**
- **Consumes:** `_extract_generic`, `_TS_CONFIG`/`_TSX_CONFIG`.
- **Produces:** `def extract_typescript(path: Path) -> Extraction:` (selects `_TS_CONFIG` for `.ts/.mts/.cts`, `_TSX_CONFIG` for `.tsx`).

- [ ] Create fixtures `tests/archgraph/fixtures/ts_sample/user.ts`:
  ```typescript
  import { formatName } from "./format";

  export interface User { id: number; name: string; }

  export class Account {
    constructor(private user: User) {}
    label(): string { return formatName(this.user.name); }
  }
  ```
  and `tests/archgraph/fixtures/ts_sample/format.ts`:
  ```typescript
  export function formatName(n: string): string { return n.trim(); }
  ```
- [ ] Write `test_extract_typescript.py::test_extracts_class_interface` asserting `type`-kind nodes `User` and `Account`, `symbol`-kind node `label`.
- [ ] Write `test_extract_typescript.py::test_extracts_named_import_edge` asserting an `imports` edge from `user.ts` to the `formatName` symbol id (target keyed by `_file_stem("format.ts")`), method EXTRACTED.
- [ ] Write `test_extract_typescript.py::test_tsx_parses` — add `fixtures/ts_sample/widget.tsx` with a JSX expression calling a function; assert the call edge is captured (proving `language_tsx` is used, not `language_typescript`).
- [ ] Run `pytest tests/archgraph/test_extract_typescript.py -q` → FAIL.
- [ ] Extend `_extract_generic` (or add TS-specific handling in `_extract_generic`) so `interface_declaration`/`class_declaration` → `type` nodes and `import_statement` named specifiers → symbol-targeted `imports` edges. Implement `extract_typescript` with the `.tsx`→`_TSX_CONFIG` branch. Register both in the registry dispatch.
- [ ] Run `pytest tests/archgraph/test_extract_typescript.py -q` → PASS.
- [ ] Commit: `feat(archgraph): typescript/tsx AST extractor (classes, interfaces, imports)`.

---

### Task 5 — Mapper: code dicts → PER-317 candidate objects (`mapper.py`)

**Files:** `apps/backend/archivum/archgraph/mapper.py`, `tests/archgraph/conftest.py` (add `FakeValidationLayer`), `tests/archgraph/test_mapper.py`

**Interfaces:**
- **Consumes:** `Extraction`, `CodeNode`, `CodeEdge`, PER-317 `write_candidates` (or `FakeValidationLayer`), a `chunk_id` per file (from a Chunk write for the file's source span).
- **Produces:**
  ```python
  # archgraph/mapper.py
  @dataclass
  class CandidateEntity:  id: str; kind: str; name: str; scope: str; confidence: float; extraction_method: str; provenance: list[Provenance]
  @dataclass
  class CandidateArtifact: ...   # kind in {file,repo,commit,pr,test,deployment}
  @dataclass
  class CandidateRelationship: id: str; src_id: str; dst_id: str; rel_type: str; scope: str; confidence: float; extraction_method: str; provenance: list[Provenance]
  @dataclass
  class Provenance: chunk_id: str; span: str; extraction_method: str

  def map_extraction(ext: Extraction, *, scope: str, chunk_id: str) -> list[Candidate]: ...
  # Candidate = CandidateEntity | CandidateArtifact | CandidateRelationship
  ```

- [ ] Add `FakeValidationLayer` to `tests/archgraph/conftest.py`: an async `write_candidates(conn, cands)` recording candidates and enforcing the §4 invariant (reject any candidate with empty `provenance` or missing `extraction_method`), returning a `WriteResult(written_ids=[...], rejected=[...])`.
- [ ] Write `test_mapper.py::test_maps_symbol_to_entity` — an `add` `symbol` `CodeNode` maps to a `CandidateEntity(kind="symbol")` with `scope="repo:archivum"`, one `Provenance(chunk_id=..., span="L5-L6", extraction_method="EXTRACTED")`.
- [ ] Write `test_mapper.py::test_maps_file_to_artifact` — the `file` node maps to a `CandidateArtifact(kind="file")`.
- [ ] Write `test_mapper.py::test_maps_edge_to_relationship_preserves_method` — a `calls` `CodeEdge(method=INFERRED)` maps to `CandidateRelationship(rel_type="calls", extraction_method="INFERRED")`.
- [ ] Write `test_mapper.py::test_validation_rejects_no_provenance` — feed a candidate with `provenance=[]` to `FakeValidationLayer.write_candidates`, assert it lands in `rejected`.
- [ ] Run `pytest tests/archgraph/test_mapper.py -q` → FAIL.
- [ ] Implement `mapper.py`: `_NODE_KIND_TO_CANDIDATE` split (`file/repo/commit/pr/test/deployment` → Artifact, else Entity), `map_extraction` building candidates with provenance from each node/edge `source_location`. Before running, `rg "def write_candidates" apps/backend` and reconcile the adapter to the real signature if present (else keep the fake).
- [ ] Run `pytest tests/archgraph/test_mapper.py -q` → PASS.
- [ ] Commit: `feat(archgraph): map code extractions to PER-317 candidate objects`.

---

### Task 6 — Content-hash AST cache (`cache.py`)

**Files:** `apps/backend/archivum/archgraph/cache.py`, `tests/archgraph/test_cache.py`

**Interfaces:**
- **Produces:**
  ```python
  # archgraph/cache.py
  EXTRACTOR_VERSION: str            # bump to invalidate all AST cache entries
  def content_hash(path: Path) -> str: ...             # sha256 of file bytes
  def load_cached(path: Path, cache_dir: Path) -> Extraction | None: ...
  def save_cached(path: Path, ext: Extraction, cache_dir: Path) -> None: ...
  # entries at cache_dir/ast/v{EXTRACTOR_VERSION}/{content_hash}.json
  ```

- [ ] Write `test_cache.py::test_roundtrip` — `save_cached(f, ext, d)` then `load_cached(f, d)` returns an equal `Extraction` (nodes/edges reconstructed with correct `ExtractionMethod`).
- [ ] Write `test_cache.py::test_miss_on_changed_content` — cache under original bytes, mutate the file's bytes, assert `load_cached` returns `None` (hash changed).
- [ ] Write `test_cache.py::test_version_namespacing` — an entry written under `EXTRACTOR_VERSION="v1"` is not returned when the module reports `v2` (monkeypatch `EXTRACTOR_VERSION`).
- [ ] Run `pytest tests/archgraph/test_cache.py -q` → FAIL.
- [ ] Implement `cache.py`: `content_hash` = `hashlib.sha256(path.read_bytes()).hexdigest()`; serialize `Extraction` to JSON (enum → `.value`, deserialize back); path `cache_dir/ast/v{EXTRACTOR_VERSION}/{hash}.json`; atomic write via temp file + `os.replace`.
- [ ] Run `pytest tests/archgraph/test_cache.py -q` → PASS.
- [ ] Commit: `feat(archgraph): content-hash AST cache namespaced by extractor version`.

---

### Task 7 — Cross-file symbol resolution (`resolve.py`)

**Files:** `apps/backend/archivum/archgraph/resolve.py`, `tests/archgraph/test_resolve.py`

**Interfaces:**
- **Consumes:** `list[Extraction]` (one per file in a repo).
- **Produces:**
  ```python
  # archgraph/resolve.py
  def resolve_cross_file(extractions: list[Extraction]) -> list[CodeEdge]: ...
  # returns NEW edges only: unresolved same-file calls now pointed at a real
  # cross-file symbol node, method=INFERRED; a name matching >1 target -> AMBIGUOUS
  ```

- [ ] Write `test_resolve.py::test_resolves_imported_call_inferred` — two Python fixtures: `a.py` `from b import helper; def run(): helper()` and `b.py` `def helper(): pass`. Extract both; assert `resolve_cross_file` yields a `calls` edge `a.run -> b.helper` with `method == INFERRED`.
- [ ] Write `test_resolve.py::test_ambiguous_on_collision` — two files each define `helper`; a third calls an unqualified `helper()` with no import; assert the produced edge is `method == AMBIGUOUS` (or emitted to both targets flagged AMBIGUOUS).
- [ ] Write `test_resolve.py::test_no_duplicate_of_extracted` — an already-EXTRACTED intra-file call is not re-emitted as INFERRED.
- [ ] Run `pytest tests/archgraph/test_resolve.py -q` → FAIL.
- [ ] Implement `resolve_cross_file`: build a symbol table `name -> [node_id]` across all extractions; for each unresolved call target (a `calls` edge whose `target` matches no local symbol node), look up the name; exactly one match → new `INFERRED` edge; >1 → `AMBIGUOUS`; zero → drop (external). Dedupe against existing EXTRACTED edges by `(source,target,relation)`.
- [ ] Run `pytest tests/archgraph/test_resolve.py -q` → PASS.
- [ ] Commit: `feat(archgraph): cross-file symbol resolution emitting INFERRED/AMBIGUOUS edges`.

---

### Task 8 — Repo snapshots: repo/commit Artifacts (`repo.py`)

**Files:** `apps/backend/archivum/archgraph/repo.py`, `tests/archgraph/conftest.py` (add `git_repo` fixture), `tests/archgraph/test_repo.py`

**Interfaces:**
- **Consumes:** a repo path (git working tree).
- **Produces:**
  ```python
  # archgraph/repo.py
  @dataclass(frozen=True)
  class RepoSnapshot:
      repo_id: str          # _make_id(remote_url or repo path basename)
      commit_sha: str       # HEAD sha (or "working-tree" if not a git repo)
      root: Path
      remote_url: str | None
  def snapshot_repo(root: Path) -> RepoSnapshot: ...
  def collect_files(root: Path) -> list[Path]: ...   # CODE_SUFFIXES filtered, .git/node_modules skipped
  def repo_artifacts(snap: RepoSnapshot) -> list[CandidateArtifact]: ...  # repo + commit + in_commit edge
  ```

- [ ] Add a `git_repo` fixture to `conftest.py`: `tmp_path`, `git init`, copy `py_sample`, `git add -A && git commit -m init` (via `subprocess`, guarded skip if git absent).
- [ ] Write `test_repo.py::test_snapshot_reads_head_sha` — `snapshot_repo(git_repo).commit_sha` is a 40-char hex string.
- [ ] Write `test_repo.py::test_collect_files_filters` — `collect_files` returns only `.py` files under `py_sample`, excludes anything under `.git/`.
- [ ] Write `test_repo.py::test_repo_artifacts_shapes` — `repo_artifacts` yields a `repo`-kind and a `commit`-kind `CandidateArtifact` plus a relationship linking commit → repo.
- [ ] Write `test_repo.py::test_non_git_dir_working_tree` — a plain dir (no `.git`) → `commit_sha == "working-tree"`, no crash.
- [ ] Run `pytest tests/archgraph/test_repo.py -q` → FAIL.
- [ ] Implement `repo.py`: `snapshot_repo` shells `git rev-parse HEAD` / `git config --get remote.origin.url` (best-effort, fallback to working-tree); `collect_files` walks pruning `.git`, `node_modules`, `.venv`; `repo_artifacts` builds candidates with provenance anchored to a repo-level chunk (span `"L0"`).
- [ ] Run `pytest tests/archgraph/test_repo.py -q` → PASS.
- [ ] Commit: `feat(archgraph): repo/commit snapshot artifacts and file collection`.

---

### Task 9 — Cross-repository resolver (`cross_repo.py`)

**Files:** `apps/backend/archivum/archgraph/cross_repo.py`, `tests/archgraph/test_cross_repo.py`

**Interfaces:**
- **Consumes:** L1 query access (async, over the SQLite conn) to Entity rows (`kind`, `name`, `scope`) — or a fake in tests.
- **Produces:**
  ```python
  # archgraph/cross_repo.py
  async def resolve_cross_repo(conn) -> list[CandidateRelationship]: ...
  # links same symbol/package Entity across different repo scopes: emits
  # `same_symbol_as` / `depends_on` relationships, method=INFERRED, AMBIGUOUS on weak match
  def _match_key(kind: str, name: str) -> str: ...   # normalization key for cross-repo identity
  ```

- [ ] Write `test_cross_repo.py::test_links_same_package_across_repos` — seed a fake L1 with a `package` Entity `requests` in `scope="repo:a"` and another `requests` in `scope="repo:b"`; assert `resolve_cross_repo` emits a `depends_on`/`same_symbol_as` `CandidateRelationship` between them with `method == INFERRED`.
- [ ] Write `test_cross_repo.py::test_no_link_within_same_repo` — two `requests` entities in the same scope produce no cross-repo edge.
- [ ] Write `test_cross_repo.py::test_ambiguous_on_common_name` — a very common symbol name (e.g. `main`) shared across 3+ repos is emitted `AMBIGUOUS`, not INFERRED (guard against god-node linkage).
- [ ] Run `pytest tests/archgraph/test_cross_repo.py -q` → FAIL.
- [ ] Implement `resolve_cross_repo`: query entities grouped by `_match_key(kind, name)` (packages/types are strong keys; bare symbols weak); across ≥2 distinct scopes with a strong key → INFERRED; weak key or ≥3 scopes with a common name → AMBIGUOUS. Provenance = a synthetic resolver chunk citing both entity ids.
- [ ] Run `pytest tests/archgraph/test_cross_repo.py -q` → PASS.
- [ ] Commit: `feat(archgraph): cross-repository entity resolver linking symbols/packages across repos`.

---

### Task 10 — Evidence bridging (`bridge.py`)

**Files:** `apps/backend/archivum/archgraph/bridge.py`, `tests/archgraph/test_bridge.py`

**Interfaces:**
- **Consumes:** L1 query access to non-code evidence already landed by PER-316/317 — `Artifact(kind in {pr, deployment})`, `Event`, conversation `Chunk`s — plus code `Artifact(kind=commit/file)`.
- **Produces:**
  ```python
  # archgraph/bridge.py
  async def bridge_evidence(conn) -> list[CandidateRelationship]: ...
  # links code symbols/commits to PR/conversation/deploy evidence:
  #   commit  --shipped_in-->  PR        (EXTRACTED if PR body cites the sha, else INFERRED)
  #   symbol  --decided_in-->  conversation Chunk (INFERRED, when chunk text names the symbol)
  #   commit  --deployed_in--> deployment Event   (INFERRED, by time/sha proximity)
  ```

- [ ] Write `test_bridge.py::test_commit_shipped_in_pr_extracted` — fake L1 with a `commit` Artifact (sha `abc123…`) and a `pr` Artifact whose evidence chunk text contains that sha; assert a `shipped_in` `CandidateRelationship` with `method == EXTRACTED`.
- [ ] Write `test_bridge.py::test_symbol_decided_in_conversation_inferred` — a `symbol` Entity `retrieve_code` and a conversation chunk mentioning `retrieve_code`; assert a `decided_in` edge `method == INFERRED`.
- [ ] Write `test_bridge.py::test_no_bridge_without_evidence` — no matching evidence → no edges (never fabricate; spec §6.5).
- [ ] Run `pytest tests/archgraph/test_bridge.py -q` → FAIL.
- [ ] Implement `bridge_evidence`: query PR/deploy artifacts and conversation chunks; match commit shas by substring (EXTRACTED) and symbol names by token match in chunk text (INFERRED); emit relationships with provenance citing the bridging chunk. Guard: require a real evidence chunk id on every emitted edge.
- [ ] Run `pytest tests/archgraph/test_bridge.py -q` → PASS.
- [ ] Commit: `feat(archgraph): evidence bridging linking code to PRs, conversations, deploys`.

---

### Task 11 — Code lexical index: trigram + IDF (`lexical.py`)

**Files:** `apps/backend/archivum/archgraph/lexical.py`, `tests/archgraph/test_lexical.py`

**Interfaces:**
- **Consumes:** code `Entity`/`Artifact` rows from L1 (id, name/label, kind).
- **Produces:**
  ```python
  # archgraph/lexical.py  (L2 index, SQLite-backed, rebuildable)
  def _trigrams(text: str) -> set[str]: ...
  async def build_lexical_index(conn, code_nodes: list[tuple[str, str]]) -> None: ...  # (id, text)
  async def trigram_candidates(conn, query: str) -> set[str]: ...   # superset of node ids
  async def score_nodes(conn, query: str, candidate_ids: set[str]) -> list[tuple[float, str]]: ...
  # score = sum over query terms of IDF(term) * (1 if term in node text else 0), desc
  ```

- [ ] Write `test_lexical.py::test_trigrams` asserting `_trigrams("calc")` == `{"cal","alc"}` (and short-string fallback for <3 chars returns `{"calc"}`-style whole-string key).
- [ ] Write `test_lexical.py::test_candidates_superset` — index nodes `retrieve_code`, `format_name`, `add`; `trigram_candidates(conn, "retrieve")` includes `retrieve_code` and excludes `add`.
- [ ] Write `test_lexical.py::test_idf_ranks_rare_higher` — build index where `add` appears in many node texts and `hypotenuse` in one; `score_nodes` ranks a `hypotenuse` match above a common-term match.
- [ ] Run `pytest tests/archgraph/test_lexical.py -q` → FAIL.
- [ ] Implement `lexical.py`: create `code_trigram(trigram TEXT, node_id TEXT)` and `code_node_text(node_id TEXT PK, text TEXT)` tables; `build_lexical_index` populates them; `trigram_candidates` intersects postings for the query's trigrams; `score_nodes` computes IDF from document frequency in `code_node_text` and sums term weights. **No Qdrant, no vectors** — assert this in a comment referencing Global Constraint 3.
- [ ] Run `pytest tests/archgraph/test_lexical.py -q` → PASS.
- [ ] Commit: `feat(archgraph): trigram+IDF lexical index for code retrieval (no vectors)`.

---

### Task 12 — Code retrieval: seed → BFS → lexical score → subgraph (`retrieval.py`)

**Files:** `apps/backend/archivum/archgraph/retrieval.py`, `tests/archgraph/test_retrieval.py`

**Interfaces:**
- **Consumes:** `lexical.score_nodes`/`trigram_candidates`, L2 graph adjacency (Kuzu via `db/graph.py`, or a fake adjacency in tests), L1 for node/edge metadata (scope, method, confidence, provenance).
- **Produces:**
  ```python
  # archgraph/retrieval.py
  @dataclass
  class ScopedSubgraph:
      nodes: list[dict]   # each: id, label, kind, scope, confidence, extraction_method, citation
      edges: list[dict]   # each: source, target, relation, extraction_method, confidence
  async def retrieve_code(
      conn, query: str, *, depth: int = 2, max_nodes: int = 10, scope: str | None = None,
      relations: frozenset[str] | None = None,
  ) -> ScopedSubgraph: ...
  # 1. lexical seed: top-3 nodes by score_nodes over trigram_candidates
  # 2. BFS: depth-limited, relation-filtered neighborhood from seeds
  # 3. cap to max_nodes by seed-distance then score; annotate each with citation+method+confidence
  ```

- [ ] Write `test_retrieval.py::test_seeds_from_lexical` — index a small graph; `retrieve_code(conn, "hypot")` seeds on the `hypot` symbol node.
- [ ] Write `test_retrieval.py::test_bfs_expands_neighbors` — assert the returned subgraph includes `hypot`'s `calls` neighbor `add` at depth 2.
- [ ] Write `test_retrieval.py::test_respects_max_nodes_and_scope` — `max_nodes=3` returns ≤3 nodes; `scope="repo:a"` excludes `repo:b` nodes.
- [ ] Write `test_retrieval.py::test_nodes_carry_method_and_citation` — every returned node dict has `extraction_method` and a non-empty `citation` (provenance), satisfying spec §8.
- [ ] Run `pytest tests/archgraph/test_retrieval.py -q` → FAIL.
- [ ] Implement `retrieve_code`: call `trigram_candidates` → `score_nodes` → take top-3 seeds; BFS over L2 adjacency (depth-limited, filtered by `relations` and `scope`); truncate to `max_nodes` ordered by (distance, score); hydrate node/edge metadata + provenance citation from L1.
- [ ] Run `pytest tests/archgraph/test_retrieval.py -q` → PASS.
- [ ] Commit: `feat(archgraph): code retrieval via lexical seed + BFS neighborhood → scoped subgraph`.

---

### Task 13 — Full repo ingest pipeline (`ingest.py`)

**Files:** `apps/backend/archivum/archgraph/ingest.py`, `tests/archgraph/test_ingest.py`

**Interfaces:**
- **Consumes:** everything above + PER-317 `write_candidates` (or `FakeValidationLayer`) + `rebuild_indexes` + chunk write.
- **Produces:**
  ```python
  # archgraph/ingest.py
  @dataclass
  class IngestReport:
      files: int; nodes: int; edges: int; rejected: int; cache_hits: int
  async def ingest_repo(conn, root: Path, *, scope: str, cache_dir: Path,
                        update: bool = False) -> IngestReport: ...
  ```

- [ ] Write `test_ingest.py::test_full_ingest_lands_in_l1` — `ingest_repo(conn, py_sample_repo, scope="repo:test", cache_dir=tmp)` (with `FakeValidationLayer`) writes Entity/Artifact/Relationship candidates; assert `report.nodes > 0` and the `Calculator` entity is present in the fake L1.
- [ ] Write `test_ingest.py::test_second_run_uses_cache` — run twice unchanged; assert second `report.cache_hits == report.files` and no new LLM/parse work (parse counter monkeypatched).
- [ ] Write `test_ingest.py::test_all_edges_have_method` — assert every written relationship candidate has `extraction_method` in the enum (Global Constraint 4).
- [ ] Run `pytest tests/archgraph/test_ingest.py -q` → FAIL.
- [ ] Implement `ingest_repo`: `snapshot_repo` → `repo_artifacts` → `collect_files` → per file `load_cached` else `extract_file` + `save_cached` → `resolve_cross_file` → per-file Chunk write → `map_extraction` → `write_candidates` → `resolve_cross_repo` → `bridge_evidence` → `write_candidates` → `build_lexical_index` → `rebuild_indexes`. Tally `IngestReport`.
- [ ] Run `pytest tests/archgraph/test_ingest.py -q` → PASS.
- [ ] Commit: `feat(archgraph): full deterministic repo ingest pipeline into L1`.

---

### Task 14 — Incremental re-index + dangling pruning (`ingest.py` `--update`)

**Files:** `apps/backend/archivum/archgraph/ingest.py`, `tests/archgraph/test_ingest.py` (extend)

**Interfaces:**
- **Consumes:** prior L1 state + git diff of changed files.
- **Produces:**
  ```python
  # archgraph/ingest.py
  def changed_files(root: Path, since_sha: str | None) -> tuple[list[Path], list[Path]]: ...  # (changed, deleted)
  async def prune_dangling(conn, deleted_files: list[Path], scope: str) -> int: ...  # removes objects+edges whose source file is gone
  ```

- [ ] Write `test_ingest.py::test_update_reextracts_only_changed` — ingest repo; modify one file; `ingest_repo(..., update=True)`; assert only the changed file was re-extracted (parse counter == 1) while others hit cache.
- [ ] Write `test_ingest.py::test_prune_removes_deleted_file_objects` — delete a file, run update; assert its Entity/Artifact rows and any edges referencing them are removed from L1 (fake), and dangling cross-file edges pointing at them are pruned.
- [ ] Write `test_ingest.py::test_prune_keeps_live_objects` — untouched files' objects survive the prune.
- [ ] Run `pytest tests/archgraph/test_ingest.py -q` → FAIL.
- [ ] Implement `changed_files` (git `diff --name-status since_sha..HEAD`, fallback to mtime vs cache when non-git); in `ingest_repo(update=True)` extract only changed, call `prune_dangling` for deleted, then re-run resolvers over the affected scope and `rebuild_indexes`.
- [ ] Run `pytest tests/archgraph/test_ingest.py -q` → PASS.
- [ ] Commit: `feat(archgraph): incremental re-index of changed files with dangling pruning`.

---

### Task 15 — Git-hook / repo-ingest CLI entrypoint (`hook.py`)

**Files:** `apps/backend/archivum/archgraph/hook.py`, `apps/backend/pyproject.toml` (`[project.scripts]`), `tests/archgraph/test_hook.py`

**Interfaces:**
- **Produces:**
  ```python
  # archgraph/hook.py
  def main(argv: list[str] | None = None) -> int: ...
  # usage: archivum-archgraph ingest <repo_path> [--scope repo:name] [--update]
  # also exposes install_post_commit_hook(repo: Path) writing .git/hooks/post-commit
  def install_post_commit_hook(repo: Path) -> Path: ...
  ```

- [ ] Write `test_hook.py::test_cli_ingest_invokes_pipeline` — `main(["ingest", str(py_sample_repo), "--scope", "repo:test"])` returns 0 and triggers `ingest_repo` (patched), asserting args pass through.
- [ ] Write `test_hook.py::test_install_post_commit_hook` — `install_post_commit_hook(git_repo)` writes an executable `.git/hooks/post-commit` whose body invokes `archivum-archgraph ingest ... --update`.
- [ ] Write `test_hook.py::test_bad_args_returns_nonzero` — `main(["nonsense"])` returns non-zero without raising.
- [ ] Run `pytest tests/archgraph/test_hook.py -q` → FAIL.
- [ ] Implement `hook.py` with `argparse` (`ingest` subcommand), an async runner opening the L1 conn via `db/sqlite.py`, and `install_post_commit_hook`; add `[project.scripts] archivum-archgraph = "archivum.archgraph.hook:main"` to `pyproject.toml`.
- [ ] Run `pytest tests/archgraph/test_hook.py -q` → PASS.
- [ ] Commit: `feat(archgraph): git-hook and CLI repo-ingest entrypoint`.

---

### Task 16 — End-to-end: extract → L1 → retrieve (`test_end_to_end.py`)

**Files:** `tests/archgraph/test_end_to_end.py`, `apps/backend/archivum/archgraph/__init__.py` (public re-exports)

**Interfaces:**
- **Produces:** `archgraph.__init__` re-exports `ingest_repo`, `retrieve_code`, `ScopedSubgraph`, `ExtractionMethod`.

- [ ] Write `test_end_to_end.py::test_ingest_then_retrieve` — ingest `py_sample` into a fake/real L1, then `retrieve_code(conn, "hypot")` returns a `ScopedSubgraph` containing `hypot`, its `calls` edge to `add` (method present), and a provenance citation on each node — proving the whole deterministic path with zero LLM calls.
- [ ] Write `test_end_to_end.py::test_cross_repo_bridge_visible_in_retrieval` — ingest two repos sharing a `package`; assert a cross-repo `depends_on` edge (INFERRED) appears in a retrieval scoped to span both.
- [ ] Write `test_end_to_end.py::test_no_llm_call` — patch `anthropic` client to raise on use; run full ingest+retrieve; assert it never touched the LLM (Global Constraint 1).
- [ ] Run `pytest tests/archgraph/test_end_to_end.py -q` → FAIL (any gaps).
- [ ] Fill gaps; add `archgraph/__init__.py` re-exports.
- [ ] Run `pytest tests/archgraph/ -q` (whole suite) → PASS.
- [ ] Commit: `test(archgraph): end-to-end extract→L1→retrieve with zero-LLM assertion`.

---

## Self-Review (completed inline)

- **Spec coverage:** §7 deterministic extractor (T2–T4, zero-LLM asserted T13/T16), code-typed Entity/Artifact/Relationship with method labels (T5, T13-assert), cross-repo resolver (T9), evidence bridging (T10), graph+lexical retrieval no-vectors (T11–T12, asserted). §5 AST cache (T6), `--update` incremental + dangling prune (T14). §4 invariant (≥1 provenance/confidence/method) enforced in `FakeValidationLayer` (T5) and asserted (T13). §8 scoped subgraph with citation+method+confidence (T12). Git-hook entrypoint (T15). All covered.
- **Placeholder scan:** no `TODO`/`...`/`TBD` left as implementation; every code block is concrete. The only stubbed surface is PER-317's validation layer, explicitly isolated to `mapper.py` + `FakeValidationLayer` with a documented reconciliation step (Upstream Dependencies + T5).
- **Type consistency:** `ExtractionMethod` (enum) used everywhere for edge method; `CodeNode`/`CodeEdge`/`Extraction` produced by T1 and consumed by T3–T7; `CandidateEntity/Artifact/Relationship`/`Provenance` produced by T5 and consumed by T8–T10, T13; `ScopedSubgraph` produced by T12, consumed by T16. `LanguageConfig` produced by T2, consumed by T3–T4. Signatures match across producer/consumer tasks.
- **Fix applied inline:** clarified that Task 4 extends `_extract_generic` (not a divergent path) so the TS extractor reuses the Python task's walker; clarified cross-repo AMBIGUOUS guard against god-node linkage (T9); made `changed_files` non-git fallback explicit (T14).
