# Editable Agent Memory Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Archivum into a person-centered second brain where the default root node is always me: my projects, thoughts, sources, decisions, relationships, and agent context orbit a durable profile of who I am and what I care about.

**Architecture:** Keep markdown pages as the primary human editing surface, but stop treating raw markdown as the only knowledge model. Introduce a canonical evidence/object layer centered on a stable `person:self` object that records sources, editable notes, projects, thoughts, decisions, extracted entities, claims, relationships, provenance, confidence, and temporal metadata; then rebuild Qdrant, Kuzu, and code lexical indexes as derived projections. Agent tools consume scoped context packages that default to expanding from `person:self`, so retrieval feels like zooming into my life and work rather than querying an anonymous corpus.

**Tech Stack:** FastAPI, SQLite, Kuzu, Qdrant, aiosqlite, existing `archivum.archgraph`, existing ingest/query/MCP APIs, React/Vite frontend, pytest, Vitest.

## Product Description

Archivum is a self-hosted, editable second brain built around a living center node: me. Notes, projects, code, conversations, links, decisions, people, and recurring thoughts are not just files in a vault; they are connected back to my identity, goals, responsibilities, preferences, history, and current focus. The UI should make that obvious: the graph opens from me, agent context is scoped through me unless I choose another seed, and every object can answer “how does this relate to me?”

The frontend can still present itself as an Obsidian-style alternative because editing markdown remains the core human workflow. The backend should make the experience deeper than Obsidian: provenance-aware memory for agents, deterministic graph structure for code and projects, and scoped retrieval that treats my life and work as the organizing principle.

## Global Constraints

- Public product language stays focused on a self-hosted, server-hosted Obsidian-style second brain.
- Do not present Archivum publicly as Archgraph, GraphRAG, Tencent memory, or project memory.
- The default graph and retrieval root is `person:self`; users can change seeds, but the product should first feel centered on the owner.
- Projects, thoughts, sources, code, people, tasks, decisions, and questions must be linkable back to `person:self` through typed relationships.
- Markdown remains directly editable by humans and exportable as files.
- Canonical agent memory objects must carry provenance, confidence, extraction method, and source scope.
- Qdrant and Kuzu remain rebuildable derived indexes.
- Code retrieval uses Graphify-style deterministic structure plus lexical scoring, not dense vectors.
- Natural-language retrieval may use hybrid keyword, vector, graph, and temporal signals.
- Every agent answer must cite evidence or declare insufficient evidence.
- MCP tools must expose scoped retrieval and graph access without dumping the whole vault by default.

---

## File Structure

- Modify `apps/backend/archivum/store/schema.py`: add L1 knowledge/evidence tables.
- Create `apps/backend/archivum/knowledge/models.py`: typed Pydantic/dataclass models for sources, objects, claims, relationships, citations, context packages.
- Create `apps/backend/archivum/knowledge/personal_root.py`: initialize and maintain the owner profile, root relationships, and default graph/retrieval seed.
- Create `apps/backend/archivum/knowledge/repository.py`: SQLite read/write layer for canonical knowledge objects.
- Create `apps/backend/archivum/knowledge/validation.py`: provenance/confidence/extraction-method validation.
- Create `apps/backend/archivum/knowledge/projections.py`: rebuild Qdrant, Kuzu, FTS, and code lexical projections from canonical rows.
- Modify `apps/backend/archivum/ingest/pipeline.py`: write markdown/file/url ingest results into the canonical knowledge repository.
- Modify `apps/backend/archivum/archgraph/ingest.py`: replace temporary validation sink assumptions with the canonical repository interface.
- Create `apps/backend/archivum/retrieval/context.py`: scoped context package builder.
- Create `apps/backend/archivum/retrieval/hybrid.py`: natural-language hybrid retrieval.
- Modify `apps/backend/archivum/api/query.py`: answer from context packages.
- Create `apps/backend/archivum/api/context.py`: `/api/context-package`, `/api/retrieve`, `/api/ask`.
- Modify `apps/backend/archivum/mcp/server.py`: expose context package and scoped graph tools.
- Modify `apps/backend/archivum/db/graph.py`: support provenance-aware object/relationship projections while preserving existing page graph endpoints.
- Modify `apps/frontend/src/api.ts`: add context package, entity, citation, and scoped graph clients.
- Create `apps/frontend/src/components/SelfNodeHeader.tsx`: persistent owner-centered graph/search context affordance.
- Create `apps/frontend/src/components/ProvenanceDrawer.tsx`: inspect citations, spans, confidence, extraction method.
- Modify `apps/frontend/src/components/Editor/Editor.tsx`: show agent-derived suggestions as reviewable overlays, not silent edits.
- Modify `apps/frontend/src/components/GraphView.tsx`: support scoped graph exploration seeded from pages/entities/answers.
- Add tests under `tests/knowledge/`, `tests/retrieval/`, `tests/api/`, and existing `tests/archgraph/`.
- Add frontend tests under `apps/frontend/src/**/__tests__/`.

---

### Task 0: Personal Root Ontology

**Files:**
- Create: `apps/backend/archivum/knowledge/personal_root.py`
- Test: `tests/knowledge/test_personal_root.py`

**Interfaces:**
- Consumes: `KnowledgeRepository`, `KnowledgeObject`, `KnowledgeRelationship`, `Citation`.
- Produces:
  - `SELF_ID = "person:self"`
  - `ensure_personal_root(repo: KnowledgeRepository, *, display_name: str = "Me", wiki_id: str = "default") -> KnowledgeObject`
  - `link_to_self(repo: KnowledgeRepository, object_id: str, rel_type: str, *, citation: Citation, confidence: float = 1.0) -> KnowledgeRelationship`
  - canonical relationship vocabulary: `owns_project`, `authored_thought`, `cares_about`, `decided`, `works_on`, `knows_person`, `saved_source`, `asked_question`, `uses_code`

- [ ] **Step 1: Write the failing personal root tests**

```python
import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


@pytest.mark.asyncio
async def test_ensure_personal_root_creates_me_node():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        root = await ensure_personal_root(repo, display_name="Pranav", wiki_id="default")
        assert root.id == SELF_ID
        assert root.kind == "person"
        assert root.label == "Pranav"
        assert root.properties["is_owner"] is True


@pytest.mark.asyncio
async def test_link_project_to_self():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await ensure_personal_root(repo, display_name="Me", wiki_id="default")
        await repo.upsert_object(KnowledgeObject(
            id="project:archivum",
            kind="project",
            label="Archivum",
            scope="wiki:default",
            confidence=1.0,
            extraction_method="USER_AUTHORED",
            citations=[Citation(source_id="page:archivum", chunk_id="page:archivum", span_start=0, span_end=8, quote="Archivum")],
            properties={},
        ))
        rel = await link_to_self(
            repo,
            "project:archivum",
            "owns_project",
            citation=Citation(source_id="page:archivum", chunk_id="page:archivum", span_start=0, span_end=8, quote="Archivum"),
        )
        assert rel.src_id == SELF_ID
        assert rel.dst_id == "project:archivum"
        assert rel.rel_type == "owns_project"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_personal_root.py -q`

Expected: FAIL because `personal_root.py` does not exist.

- [ ] **Step 3: Implement personal root helpers**

Create `SELF_ID`, relationship constants, `ensure_personal_root`, and `link_to_self`. The self object must be `kind="person"`, `scope=f"wiki:{wiki_id}"`, `extraction_method="USER_AUTHORED"`, `confidence=1.0`, and include `properties={"is_owner": True}`.

- [ ] **Step 4: Run personal root tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_personal_root.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/knowledge/personal_root.py tests/knowledge/test_personal_root.py
git commit -m "feat(knowledge): add owner-centered root ontology"
```

---

### Task 1: Canonical Knowledge Models

**Files:**
- Create: `apps/backend/archivum/knowledge/__init__.py`
- Create: `apps/backend/archivum/knowledge/models.py`
- Test: `tests/knowledge/test_models.py`

**Interfaces:**
- Consumes: no new project interfaces.
- Produces:
  - `ExtractionMethod = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS", "USER_AUTHORED"]`
  - `Citation(source_id: str, chunk_id: str, span_start: int | None, span_end: int | None, quote: str | None)`
  - `KnowledgeObject(id: str, kind: str, label: str, scope: str, confidence: float, extraction_method: ExtractionMethod, citations: list[Citation], properties: dict[str, Any])`
  - `KnowledgeRelationship(id: str, src_id: str, dst_id: str, rel_type: str, scope: str, confidence: float, extraction_method: ExtractionMethod, citations: list[Citation], properties: dict[str, Any])`
  - `ContextPackage(query: str, seeds: list[str], nodes: list[ContextNode], edges: list[ContextEdge], citations: list[Citation], insufficient_evidence: bool, reason: str | None)`

- [ ] **Step 1: Write the failing model tests**

```python
from pydantic import ValidationError

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship


def test_knowledge_object_requires_citation_for_extracted_data():
    obj = KnowledgeObject(
        id="entity:alice",
        kind="entity",
        label="Alice",
        scope="wiki:default",
        confidence=0.9,
        extraction_method="EXTRACTED",
        citations=[
            Citation(
                source_id="source:note-1",
                chunk_id="chunk:note-1:0",
                span_start=0,
                span_end=5,
                quote="Alice",
            )
        ],
        properties={"entity_type": "person"},
    )
    assert obj.label == "Alice"


def test_knowledge_relationship_rejects_empty_citations():
    try:
        KnowledgeRelationship(
            id="rel:1",
            src_id="entity:a",
            dst_id="entity:b",
            rel_type="related_to",
            scope="wiki:default",
            confidence=0.8,
            extraction_method="INFERRED",
            citations=[],
            properties={},
        )
    except ValidationError as exc:
        assert "citations" in str(exc)
    else:
        raise AssertionError("expected citations validation error")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_models.py -q`

Expected: FAIL because `archivum.knowledge.models` does not exist.

- [ ] **Step 3: Implement the models**

Create `apps/backend/archivum/knowledge/models.py` with Pydantic models and validators that require at least one citation for every object and relationship. Allow `USER_AUTHORED` so edited markdown can enter the same memory layer without pretending it was machine-extracted.

- [ ] **Step 4: Run the model tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/knowledge tests/knowledge/test_models.py
git commit -m "feat(knowledge): add canonical memory models"
```

---

### Task 2: SQLite Knowledge Store

**Files:**
- Modify: `apps/backend/archivum/store/schema.py`
- Create: `apps/backend/archivum/knowledge/repository.py`
- Test: `tests/knowledge/test_repository.py`

**Interfaces:**
- Consumes: `KnowledgeObject`, `KnowledgeRelationship`, `Citation`.
- Produces:
  - `KnowledgeRepository(conn: aiosqlite.Connection)`
  - `upsert_object(obj: KnowledgeObject) -> None`
  - `upsert_relationship(rel: KnowledgeRelationship) -> None`
  - `get_object(object_id: str) -> KnowledgeObject | None`
  - `list_objects(kind: str | None = None, scope: str | None = None, limit: int = 100) -> list[KnowledgeObject]`
  - `list_relationships(node_id: str | None = None, scope: str | None = None) -> list[KnowledgeRelationship]`

- [ ] **Step 1: Write repository tests**

```python
import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


@pytest.mark.asyncio
async def test_upsert_and_get_object_round_trip():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        obj = KnowledgeObject(
            id="entity:alice",
            kind="entity",
            label="Alice",
            scope="wiki:default",
            confidence=1.0,
            extraction_method="USER_AUTHORED",
            citations=[Citation(source_id="page:alice", chunk_id="page:alice", span_start=0, span_end=5, quote="Alice")],
            properties={"entity_type": "person"},
        )
        await repo.upsert_object(obj)
        loaded = await repo.get_object("entity:alice")
        assert loaded == obj


@pytest.mark.asyncio
async def test_relationship_query_by_node():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        rel = KnowledgeRelationship(
            id="rel:a:b",
            src_id="entity:a",
            dst_id="entity:b",
            rel_type="related_to",
            scope="wiki:default",
            confidence=0.7,
            extraction_method="INFERRED",
            citations=[Citation(source_id="page:a", chunk_id="page:a", span_start=0, span_end=10, quote="A met B")],
            properties={},
        )
        await repo.upsert_relationship(rel)
        rows = await repo.list_relationships(node_id="entity:a")
        assert [r.id for r in rows] == ["rel:a:b"]
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_repository.py -q`

Expected: FAIL because repository functions do not exist.

- [ ] **Step 3: Add schema and repository**

Add SQLite tables: `knowledge_objects`, `knowledge_relationships`, and `knowledge_citations`. Store `properties` as JSON text. Use `INSERT ... ON CONFLICT(id) DO UPDATE` and replace citations on each upsert.

- [ ] **Step 4: Run repository tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_repository.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/schema.py apps/backend/archivum/knowledge/repository.py tests/knowledge/test_repository.py
git commit -m "feat(knowledge): persist provenance-aware memory objects"
```

---

### Task 3: Markdown as Editable L3 View

**Files:**
- Modify: `apps/backend/archivum/ingest/pipeline.py`
- Modify: `apps/backend/archivum/api/pages.py`
- Test: `tests/knowledge/test_markdown_projection.py`

**Interfaces:**
- Consumes: `KnowledgeRepository.upsert_object`, `KnowledgeRepository.upsert_relationship`, `ensure_personal_root`, `link_to_self`.
- Produces:
  - `sync_page_to_knowledge(slug: str, title: str, markdown: str, wiki_id: str) -> None`
  - page objects with `kind="page"` and `extraction_method="USER_AUTHORED"`
  - wikilink relationships with `rel_type="references"` and `extraction_method="USER_AUTHORED"`
  - self relationships with `rel_type="authored_thought"` for notes and `rel_type="owns_project"` for pages marked as projects

- [ ] **Step 1: Write failing tests for editable-page sync**

```python
import aiosqlite
import pytest

from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.knowledge.personal_root import SELF_ID
from archivum.pages_to_knowledge import sync_page_to_knowledge


@pytest.mark.asyncio
async def test_markdown_page_becomes_user_authored_knowledge_object():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await sync_page_to_knowledge(repo, slug="alpha", title="Alpha", markdown="See [[Beta]].", wiki_id="default")
        obj = await repo.get_object("page:default:alpha")
        assert obj is not None
        assert obj.kind == "page"
        assert obj.extraction_method == "USER_AUTHORED"


@pytest.mark.asyncio
async def test_wikilinks_become_user_authored_relationships():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await sync_page_to_knowledge(repo, slug="alpha", title="Alpha", markdown="See [[Beta]].", wiki_id="default")
        rels = await repo.list_relationships(node_id="page:default:alpha")
        assert rels[0].dst_id == "page:default:beta"
        assert rels[0].rel_type == "references"


@pytest.mark.asyncio
async def test_markdown_page_links_back_to_self_as_authored_thought():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await sync_page_to_knowledge(repo, slug="morning-note", title="Morning Note", markdown="Thinking about focus.", wiki_id="default")
        rels = await repo.list_relationships(node_id=SELF_ID)
        assert any(r.dst_id == "page:default:morning-note" and r.rel_type == "authored_thought" for r in rels)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_markdown_projection.py -q`

Expected: FAIL because `sync_page_to_knowledge` does not exist.

- [ ] **Step 3: Implement markdown sync**

Create a small module `apps/backend/archivum/pages_to_knowledge.py`. Parse `[[wikilinks]]` with the existing wikilink slug logic used by page graph sync. Upsert the page object, ensure `person:self`, create `person:self -[:authored_thought]-> page` by default, and create one relationship per wikilink. If page frontmatter includes `type: project`, use `person:self -[:owns_project]-> page` instead. Call this function when pages are created, updated, or rebuilt.

- [ ] **Step 4: Run page and backlink tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_markdown_projection.py ../../tests/test_pages_backlinks.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/pages_to_knowledge.py apps/backend/archivum/ingest/pipeline.py apps/backend/archivum/api/pages.py tests/knowledge/test_markdown_projection.py
git commit -m "feat(knowledge): sync editable markdown into memory graph"
```

---

### Task 4: Replace Archgraph Temporary Sink

**Files:**
- Modify: `apps/backend/archivum/archgraph/mapper.py`
- Modify: `apps/backend/archivum/archgraph/ingest.py`
- Modify: `apps/backend/archivum/archgraph/hook.py`
- Test: `tests/archgraph/test_ingest.py`
- Test: `tests/archgraph/test_end_to_end.py`

**Interfaces:**
- Consumes: `KnowledgeRepository`, `KnowledgeObject`, `KnowledgeRelationship`.
- Produces: code symbols, files, repos, commits, calls/imports/references written to the canonical knowledge store.

- [ ] **Step 1: Write failing test for repository-backed archgraph ingest**

```python
import aiosqlite
import pytest

from archivum.archgraph.ingest import ingest_repo
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


@pytest.mark.asyncio
async def test_archgraph_ingest_writes_to_knowledge_repository(git_repo, cache_dir):
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        report = await ingest_repo(
            git_repo,
            scope="repo:test",
            cache_dir=cache_dir,
            knowledge=repo,
            lexical_conn=conn,
        )
        assert report.nodes > 0
        objects = await repo.list_objects(scope="repo:test")
        assert any(o.kind in {"symbol", "type", "file"} for o in objects)
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/archgraph/test_ingest.py::test_archgraph_ingest_writes_to_knowledge_repository -q`

Expected: FAIL because `ingest_repo` does not accept `knowledge`.

- [ ] **Step 3: Update archgraph mapping**

Change `map_extraction` output into canonical `KnowledgeObject` and `KnowledgeRelationship` objects or add adapter helpers named `candidate_to_knowledge_object` and `candidate_to_knowledge_relationship`. Preserve `EXTRACTED`, `INFERRED`, and `AMBIGUOUS`.

- [ ] **Step 4: Update ingest and hook**

Make `ingest_repo(..., knowledge: KnowledgeRepository, lexical_conn: aiosqlite.Connection, ...)` write accepted objects to the repository. Keep a compatibility path only inside tests that still use the fake validation layer until converted.

- [ ] **Step 5: Run archgraph suite**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/archgraph -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/archgraph tests/archgraph
git commit -m "feat(archgraph): persist code graph in canonical knowledge store"
```

---

### Task 5: Projection Rebuild Layer

**Files:**
- Create: `apps/backend/archivum/knowledge/projections.py`
- Modify: `apps/backend/archivum/db/graph.py`
- Modify: `apps/backend/archivum/db/qdrant_client.py`
- Test: `tests/knowledge/test_projections.py`

**Interfaces:**
- Consumes: `KnowledgeRepository.list_objects`, `KnowledgeRepository.list_relationships`.
- Produces:
  - `rebuild_knowledge_projections(repo: KnowledgeRepository, wiki_id: str) -> ProjectionReport`
  - Kuzu nodes for pages, entities, code symbols, files, repos.
  - Kuzu relationships with provenance metadata where supported by current schema.
  - Qdrant chunks for natural-language page/source objects only.

- [ ] **Step 1: Write failing projection tests**

```python
import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.projections import rebuild_knowledge_projections
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema


@pytest.mark.asyncio
async def test_projection_excludes_code_objects_from_qdrant(monkeypatch):
    indexed = []

    async def fake_index_page(slug, title, markdown, wiki_id="default"):
        indexed.append(slug)

    monkeypatch.setattr("archivum.knowledge.projections.index_page", fake_index_page)

    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        await repo.upsert_object(KnowledgeObject(
            id="symbol:retrieve_code",
            kind="symbol",
            label="retrieve_code",
            scope="repo:test",
            confidence=1.0,
            extraction_method="EXTRACTED",
            citations=[Citation(source_id="repo:test", chunk_id="file:a.py", span_start=0, span_end=10, quote="def retrieve_code")],
            properties={},
        ))
        report = await rebuild_knowledge_projections(repo, wiki_id="default")
        assert report.qdrant_indexed == 0
        assert indexed == []
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_projections.py -q`

Expected: FAIL because `knowledge.projections` does not exist.

- [ ] **Step 3: Implement projection report and rebuild**

Create `ProjectionReport(objects: int, relationships: int, kuzu_nodes: int, kuzu_edges: int, qdrant_indexed: int)`. Route `page`, `source`, and natural-language `claim` objects into Qdrant. Route all object and relationship types into Kuzu or the nearest existing Kuzu schema mapping while preserving existing page graph behavior.

- [ ] **Step 4: Run projection and graph tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_projections.py ../../tests/db/test_graph.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/knowledge/projections.py apps/backend/archivum/db/graph.py apps/backend/archivum/db/qdrant_client.py tests/knowledge/test_projections.py
git commit -m "feat(knowledge): rebuild derived indexes from canonical memory"
```

---

### Task 6: Scoped Context Packages

**Files:**
- Create: `apps/backend/archivum/retrieval/__init__.py`
- Create: `apps/backend/archivum/retrieval/context.py`
- Test: `tests/retrieval/test_context_package.py`

**Interfaces:**
- Consumes: `KnowledgeRepository`, `retrieve_code`, `SELF_ID`.
- Produces:
  - `ContextRequest(query: str, scope: str | None, source_type: str | None, depth: int = 2, max_nodes: int = 10, relations: list[str] | None = None, seed_ids: list[str] | None = None)`
  - `build_context_package(repo: KnowledgeRepository, request: ContextRequest) -> ContextPackage`

- [ ] **Step 1: Write failing context package tests**

```python
import aiosqlite
import pytest

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import SELF_ID, ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.retrieval.context import ContextRequest, build_context_package


@pytest.mark.asyncio
async def test_context_package_returns_bounded_cited_subgraph():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        citation = Citation(source_id="page:alpha", chunk_id="page:alpha", span_start=0, span_end=5, quote="Alpha")
        await repo.upsert_object(KnowledgeObject(id="entity:alpha", kind="entity", label="Alpha", scope="wiki:default", confidence=1.0, extraction_method="EXTRACTED", citations=[citation], properties={}))
        await repo.upsert_object(KnowledgeObject(id="entity:beta", kind="entity", label="Beta", scope="wiki:default", confidence=1.0, extraction_method="EXTRACTED", citations=[citation], properties={}))
        await repo.upsert_relationship(KnowledgeRelationship(id="rel:alpha:beta", src_id="entity:alpha", dst_id="entity:beta", rel_type="related_to", scope="wiki:default", confidence=0.8, extraction_method="INFERRED", citations=[citation], properties={}))
        package = await build_context_package(repo, ContextRequest(query="Alpha", scope="wiki:default", max_nodes=2))
        assert package.insufficient_evidence is False
        assert [n.id for n in package.nodes] == ["entity:alpha", "entity:beta"]
        assert package.edges[0].extraction_method == "INFERRED"


@pytest.mark.asyncio
async def test_context_package_defaults_to_self_when_no_seed_ids_are_given():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        root = await ensure_personal_root(repo, display_name="Me", wiki_id="default")
        citation = Citation(source_id="page:project", chunk_id="page:project", span_start=0, span_end=7, quote="Project")
        await repo.upsert_object(KnowledgeObject(id="project:one", kind="project", label="Project One", scope="wiki:default", confidence=1.0, extraction_method="USER_AUTHORED", citations=[citation], properties={}))
        await link_to_self(repo, "project:one", "owns_project", citation=citation)
        package = await build_context_package(repo, ContextRequest(query="", scope="wiki:default", max_nodes=2))
        assert package.seeds == [SELF_ID]
        assert package.nodes[0].id == root.id
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/retrieval/test_context_package.py -q`

Expected: FAIL because `retrieval.context` does not exist.

- [ ] **Step 3: Implement context builder**

If `seed_ids` is provided, start there. If the query exactly or partially matches labels, use those matches as additional seeds. If neither path produces a seed, default to `person:self`, then expand relationships breadth-first with `depth`, `max_nodes`, `scope`, and `relations`. Mark `insufficient_evidence=True` when no cited nodes are found.

- [ ] **Step 4: Run retrieval tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/retrieval/test_context_package.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/retrieval tests/retrieval/test_context_package.py
git commit -m "feat(retrieval): build cited scoped context packages"
```

---

### Task 7: Hybrid Natural-Language Retrieval

**Files:**
- Create: `apps/backend/archivum/retrieval/hybrid.py`
- Modify: `apps/backend/archivum/api/search.py`
- Modify: `apps/backend/archivum/api/query.py`
- Test: `tests/retrieval/test_hybrid.py`

**Interfaces:**
- Consumes: Qdrant search, SQLite FTS search, `build_context_package`.
- Produces:
  - `HybridHit(id: str, label: str, score: float, source: str, citation: Citation)`
  - `hybrid_retrieve(query: str, wiki_id: str, limit: int = 10) -> list[HybridHit]`

- [ ] **Step 1: Write failing score fusion test**

```python
from archivum.retrieval.hybrid import fuse_ranked_hits


def test_fuse_ranked_hits_prefers_items_found_by_multiple_channels():
    hits = fuse_ranked_hits(
        keyword=[("page:a", 0.7), ("page:b", 0.9)],
        vector=[("page:a", 0.8), ("page:c", 0.95)],
        graph=[("page:a", 0.4)],
        limit=2,
    )
    assert [h.id for h in hits] == ["page:a", "page:b"]
    assert hits[0].score > hits[1].score
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/retrieval/test_hybrid.py -q`

Expected: FAIL because `fuse_ranked_hits` does not exist.

- [ ] **Step 3: Implement deterministic rank fusion**

Use weighted reciprocal rank fusion: keyword weight `1.0`, vector weight `1.0`, graph weight `0.8`. Sort by fused score descending and id ascending. Keep the function pure so tests do not need infrastructure.

- [ ] **Step 4: Wire hybrid retrieval into query path**

Use Qdrant for natural-language source chunks, SQLite FTS for exact terms, and graph expansion from top entities/pages. Continue to cap prompt excerpts.

- [ ] **Step 5: Run query/search tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/retrieval/test_hybrid.py ../../tests/test_query.py ../../tests/db/test_qdrant.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/retrieval/hybrid.py apps/backend/archivum/api/search.py apps/backend/archivum/api/query.py tests/retrieval/test_hybrid.py
git commit -m "feat(retrieval): add hybrid memory retrieval"
```

---

### Task 8: Agent-Facing REST and MCP Tools

**Files:**
- Create: `apps/backend/archivum/api/context.py`
- Modify: `apps/backend/archivum/main.py`
- Modify: `apps/backend/archivum/mcp/server.py`
- Test: `tests/api/test_context_api.py`
- Test: `tests/mcp_tests/test_server.py`

**Interfaces:**
- Consumes: `build_context_package`, `hybrid_retrieve`.
- Produces:
  - `POST /api/context-package`
  - `POST /api/retrieve`
  - MCP tool `build_context_package(query, scope=None, depth=2, max_nodes=10, relations=None)`
  - MCP tool `retrieve_memory(query, wiki_id="default", limit=10)`

- [ ] **Step 1: Write failing REST API test**

```python
from fastapi.testclient import TestClient

from archivum.main import app


def test_context_package_route_requires_auth_or_test_auth(monkeypatch):
    client = TestClient(app)
    response = client.post("/api/context-package", json={"query": "Alpha", "max_nodes": 5})
    assert response.status_code in {200, 401}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/api/test_context_api.py -q`

Expected: FAIL because the route does not exist.

- [ ] **Step 3: Implement routes**

Add request/response Pydantic models using `ContextRequest` and `ContextPackage`. Register the router in `main.py`. Preserve existing `/api/query` behavior while internally using context packages.

- [ ] **Step 4: Add MCP tools**

Expose context package retrieval in `mcp/server.py`. Tool responses must include node ids, labels, citations, extraction methods, and confidence. Do not include full page bodies unless the tool is explicitly a read-page tool.

- [ ] **Step 5: Run API and MCP tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/api/test_context_api.py ../../tests/mcp_tests/test_server.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/api/context.py apps/backend/archivum/main.py apps/backend/archivum/mcp/server.py tests/api/test_context_api.py tests/mcp_tests/test_server.py
git commit -m "feat(api): expose scoped memory retrieval to agents"
```

---

### Task 9: Human Review Loop for Agent Suggestions

**Files:**
- Modify: `apps/backend/archivum/api/pages.py`
- Create: `apps/backend/archivum/knowledge/suggestions.py`
- Test: `tests/knowledge/test_suggestions.py`

**Interfaces:**
- Consumes: `KnowledgeRepository`.
- Produces:
  - `MemorySuggestion(id, target_id, suggestion_type, proposed_markdown, proposed_objects, citations, status)`
  - `create_suggestion(...) -> MemorySuggestion`
  - `accept_suggestion(suggestion_id: str) -> None`
  - `reject_suggestion(suggestion_id: str) -> None`

- [ ] **Step 1: Write failing suggestion lifecycle test**

```python
import aiosqlite
import pytest

from archivum.knowledge.repository import init_knowledge_schema
from archivum.knowledge.suggestions import SuggestionRepository, init_suggestion_schema


@pytest.mark.asyncio
async def test_suggestion_can_be_accepted_once():
    async with aiosqlite.connect(":memory:") as conn:
        await init_knowledge_schema(conn)
        await init_suggestion_schema(conn)
        repo = SuggestionRepository(conn)
        suggestion = await repo.create_suggestion(
            target_id="page:default:alpha",
            suggestion_type="append_section",
            proposed_markdown="## Related\n\n- [[Beta]]",
            proposed_objects=[],
            citations=[],
        )
        await repo.accept_suggestion(suggestion.id)
        loaded = await repo.get_suggestion(suggestion.id)
        assert loaded.status == "accepted"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_suggestions.py -q`

Expected: FAIL because suggestions do not exist.

- [ ] **Step 3: Implement suggestion tables and repository**

Add `memory_suggestions` with status values `pending`, `accepted`, `rejected`. Store proposed markdown and proposed objects as JSON. Acceptance should be idempotent and must not mutate page content until the frontend sends an explicit accept action.

- [ ] **Step 4: Run suggestion tests**

Run: `cd apps/backend && uv run --group dev pytest ../../tests/knowledge/test_suggestions.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/knowledge/suggestions.py tests/knowledge/test_suggestions.py
git commit -m "feat(knowledge): add reviewable agent memory suggestions"
```

---

### Task 10: Frontend Provenance and Scoped Graph UX

**Files:**
- Modify: `apps/frontend/src/api.ts`
- Create: `apps/frontend/src/components/SelfNodeHeader.tsx`
- Create: `apps/frontend/src/components/ProvenanceDrawer.tsx`
- Modify: `apps/frontend/src/components/GraphView.tsx`
- Modify: `apps/frontend/src/components/Editor/Editor.tsx`
- Test: `apps/frontend/src/components/ProvenanceDrawer.test.tsx`
- Test: `apps/frontend/src/components/GraphView.test.tsx`

**Interfaces:**
- Consumes: `/api/context-package`, `/api/retrieve`, existing page APIs.
- Produces: clickable citations, confidence/method badges, a persistent self-root context affordance, scoped graph from `person:self` or a selected page/entity/answer, reviewable suggestion UI.

- [ ] **Step 1: Write failing provenance drawer test**

```tsx
import { render, screen } from '@testing-library/react';
import { ProvenanceDrawer } from './ProvenanceDrawer';

it('renders citation method and confidence', () => {
  render(
    <ProvenanceDrawer
      open
      onClose={() => {}}
      citations={[{ source_id: 'page:alpha', chunk_id: 'page:alpha', span_start: 0, span_end: 5, quote: 'Alpha' }]}
      extractionMethod="INFERRED"
      confidence={0.72}
    />,
  );
  expect(screen.getByText('INFERRED')).toBeInTheDocument();
  expect(screen.getByText('72%')).toBeInTheDocument();
  expect(screen.getByText('Alpha')).toBeInTheDocument();
});
```

Add `apps/frontend/src/components/SelfNodeHeader.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { SelfNodeHeader } from './SelfNodeHeader';

it('shows the owner as the current graph center', () => {
  render(<SelfNodeHeader label="Me" activeScope="wiki:default" />);
  expect(screen.getByText('Me')).toBeInTheDocument();
  expect(screen.getByText('Center')).toBeInTheDocument();
});
```

- [ ] **Step 2: Run tests to verify failure**

Run: `npm test --workspace apps/frontend -- ProvenanceDrawer.test.tsx SelfNodeHeader.test.tsx`

Expected: FAIL because `ProvenanceDrawer` and `SelfNodeHeader` do not exist.

- [ ] **Step 3: Implement API types and provenance drawer**

Add TypeScript types mirroring backend context package models. Render citations compactly with method/confidence badges. Add `SelfNodeHeader` as the visual anchor for the current scope, with `Me` as the default label and “Center” as the state label. Keep public copy product-neutral: use “evidence”, “citation”, “confidence”, “center”, and “suggestion”, not Graphify or Tencent.

- [ ] **Step 4: Update graph and editor**

GraphView should request a context package with `seed_ids=["person:self"]` on first load and render only scoped nodes/edges when present. The self node should be visually distinct and centered by default. Editor should render pending suggestions as explicit accept/reject controls without auto-applying them.

- [ ] **Step 5: Run frontend tests and build**

Run: `npm test --workspace apps/frontend`

Run: `npm run build --workspace apps/frontend`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/api.ts apps/frontend/src/components/SelfNodeHeader.tsx apps/frontend/src/components/ProvenanceDrawer.tsx apps/frontend/src/components/GraphView.tsx apps/frontend/src/components/Editor/Editor.tsx apps/frontend/src/components/*.test.tsx
git commit -m "feat(frontend): add cited memory and scoped graph review UI"
```

---

### Task 11: Docs and Positioning

**Files:**
- Modify: `README.md`
- Modify: `docs/architecture/graph-model.md`
- Modify: `docs/architecture/retrieval.md`
- Modify: `docs/architecture/ingest.md`
- Modify: `docs/architecture/mcp.md`
- Modify: `docs/project/progress.md`

**Interfaces:**
- Consumes: implemented behavior from Tasks 1-10.
- Produces: accurate public docs that describe the product as editable markdown plus cited agent context.

- [ ] **Step 1: Update docs language**

Describe the system as:

```markdown
Archivum keeps markdown editable for humans while maintaining rebuildable semantic and graph indexes for search, citations, and agent context.
```

Also include the owner-centered product premise:

```markdown
Archivum organizes your notes, projects, sources, and agent context around you as the center of the graph. The default view starts from your owner profile, then lets you zoom into projects, thoughts, people, code, and decisions.
```

Do not use “Graphify”, “Tencent”, “GraphRAG”, “Archgraph”, or “project memory” in public-facing README sections.

- [ ] **Step 2: Document architecture truth**

Update architecture docs to state:

```markdown
Markdown pages are the human editing surface. Canonical knowledge rows preserve the owner profile, page-authored content, projects, thoughts, extracted entities, relationships, citations, confidence, and extraction method. Qdrant, Kuzu, FTS, and code lexical indexes are rebuildable projections. Retrieval defaults to `person:self` when the caller does not provide another seed.
```

- [ ] **Step 3: Run stale-language scan**

Run:

```bash
rg -n "scripts/[b]ootstrap|[N]eo4j|[y]ou@youremail|[L]ast updated: 2026-06|[f]eature complete|GraphRAG|Tencent|Graphify|Archgraph" -g "*.md" -g "!node_modules/**" -g "!apps/backend/.venv/**"
```

Expected: no public-facing stale matches. Private plan/spec matches are acceptable only under `docs/superpowers/`.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/architecture docs/project/progress.md
git commit -m "docs: describe editable cited memory architecture"
```

---

### Task 12: End-to-End Verification

**Files:**
- Modify tests only if failures expose real contract drift.
- Update: `docs/project/progress.md`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: verified release-readiness record.

- [ ] **Step 1: Run backend tests**

Run:

```bash
cd apps/backend && uv run --group dev pytest ../../tests -q
```

Expected: PASS.

- [ ] **Step 2: Run frontend tests and build**

Run:

```bash
npm test --workspace apps/frontend
npm run build --workspace apps/frontend
```

Expected: PASS.

- [ ] **Step 3: Run CLI tests**

Run:

```bash
npm test --workspace packages/archivum-cli
```

Expected: PASS.

- [ ] **Step 4: Docker smoke**

Run:

```bash
docker compose up -d --build
```

Expected: frontend returns 200, unauthenticated protected API returns 401, authenticated page list returns 200, MCP SSE emits endpoint event.

- [ ] **Step 5: Product smoke**

Create a markdown page with wikilinks, ingest a small source file, run a query, open the context package, inspect citations, open a scoped graph, and accept/reject one suggestion. Expected: markdown remains editable, `person:self` exists, the graph opens centered on `person:self`, the page links back to self as an authored thought or project, agent answer cites evidence, graph is bounded, and no suggestion applies without explicit user action.

- [ ] **Step 6: Update progress**

Add exact command results and manual smoke notes to `docs/project/progress.md`.

- [ ] **Step 7: Commit**

```bash
git add docs/project/progress.md
git commit -m "chore: verify editable agent memory parity"
```

---

## Parity Definition

- **Obsidian-style editability:** users can directly create, edit, link, browse, search, share, and export markdown pages without needing agent workflows.
- **Person-centered knowledge base:** the owner profile is the durable center node; projects, thoughts, people, code, sources, questions, and decisions can all explain how they relate back to me.
- **Graphify-style structure:** code and structured sources produce deterministic graph nodes/edges with content caching, lexical retrieval, provenance labels, and no vector dependency for code.
- **Tencent-style agent memory:** agents receive scoped, cited, confidence-bearing context packages built from hybrid retrieval and graph expansion, with insufficient-evidence behavior.
- **Archivum middle ground:** agent-derived structure enriches editable notes, but does not silently overwrite them; human-authored markdown and machine-extracted memory coexist in one provenance-aware backend organized around the owner.

## Self-Review

- Spec coverage: all three target inspirations plus the owner-centered premise are covered by Tasks 0-12. Person-centered structure is covered by Tasks 0, 3, 6, 10, and 12. Editability is covered by Tasks 3, 9, and 10. Graphify parity is covered by Tasks 4, 5, and 6. Tencent-style memory is covered by Tasks 6, 7, and 8.
- Placeholder scan: no task uses open-ended placeholder language such as TBD or implement later.
- Type consistency: `SELF_ID`, `KnowledgeObject`, `KnowledgeRelationship`, `Citation`, `ContextRequest`, and `ContextPackage` are introduced before downstream use.
