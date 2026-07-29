# Archivum Architecture & Canonical Knowledge Model

**Status:** Approved design (PER-314)
**Date:** 2026-07-28
**Owner:** Pranav Kannepalli
**Replaces:** Markdown-first wiki architecture; separate-Archgraph assumption

---

## 1. Purpose & Product Boundary

Archivum is a standalone, self-hosted **persistent memory and context layer** for a
person's work and life. It captures documents, conversations, code, decisions, and
events; preserves their original evidence immutably; and continuously connects them
into a queryable knowledge graph that both humans and AI agents can retrieve from,
reason over, and trace back to sources.

Archivum is **not** a wiki or note-taking app. Wiki pages, summaries, timelines,
dossiers, and context packages are **generated views** over canonical knowledge, not
the canonical data itself.

**Product surfaces:** Ask, Sources, Entities, Timeline, Graph — plus a REST API and an
MCP server for agent access (read and write).

**Archgraph** is the developer-intelligence subsystem. It is not a separate service or
store: it is the code-typed slice of the same unified graph, with its own deterministic
extractor and a cross-repository resolver (see §7).

### Scope of this decision

This document defines the architecture and canonical model only. It is the anchor for
the downstream epics: source store & ingestion (PER-315), conversation/agent capture
(PER-316), graph construction (PER-317), Archgraph (PER-318), retrieval & MCP (PER-319),
product UX (PER-320), and hardening (PER-321).

### Non-goals

- Perceo Suite integrations (tracked separately; Archivum ships standalone first).
- Multi-tenant / multi-user hosting. Single-owner self-hosted deployment only.
- Storing hidden model reasoning. Only user-visible conversation and tool activity is captured.

---

## 2. Layered Architecture

Four layers, strict one-directional dependency (each layer derives only from the one
below). This is the core decision: **canonical truth is small and durable; everything
expensive is rebuildable.**

```
L3  Generated Views      wiki pages · summaries · timelines · dossiers · context packages
        ▲ (projections, regenerable, never canonical)
L2  Derived Indexes      Qdrant (vector) · Kuzu (graph) · SQLite FTS (keyword)
        ▲ (droppable + rebuildable from L1)
L1  Canonical Knowledge  SQLite = store of record
        ▲ (sources, documents, chunks, entities, artifacts, events, claims,
           relationships, provenance, confidence, temporal validity, scopes)
L0  Immutable Evidence   content-addressed blob store on disk (sha256, versioned)
```

- **L0 — Immutable Evidence.** Every ingested source is content-addressed (sha256) and
  written once. Raw originals and their normalized forms live here. Generated knowledge
  can *never* overwrite evidence. Versioned: re-ingesting a changed source creates a new
  version, never mutates the old.
- **L1 — Canonical Knowledge (SQLite, store of record).** Relational tables hold the
  knowledge model (§4). This is the only layer that is backed up as precious data.
- **L2 — Derived Indexes (rebuildable).** Qdrant for semantic vectors, Kuzu for graph
  traversal, SQLite FTS for keyword. Any index can be dropped and rebuilt from L1 with a
  single command. No index is a source of truth.
- **L3 — Generated Views.** Everything a user reads as prose — pages, timelines,
  dossiers, context packages — is a cached projection over L1, regenerable on demand.

**Volume mapping (existing repo):** L0 + L1 → precious volumes (backed up). L2 → the
existing rebuildable `qdrant_data` / `kuzu_data` volumes. This preserves the current
precious/rebuildable split.

---

## 3. Storage Decisions (evolve in place)

Keep the existing stack — FastAPI, SQLite, Qdrant, Kuzu, Caddy, MCP. This is an
evolution, not a rewrite. Concrete changes:

| Store | Role | Change |
|-------|------|--------|
| Disk blob store (new) | L0 immutable evidence, content-addressed | **Add.** New canonical layer. |
| SQLite | L1 store of record | **Reshape** schema to the knowledge model (§4). |
| Qdrant | L2 vector index | Keep; becomes strictly derived. |
| Kuzu | L2 graph traversal index | Keep; becomes strictly derived (rebuilt from L1 edges). |
| SQLite FTS | L2 keyword index | Keep; derived. |
| Markdown `wiki_data` | was canonical | **Demote.** Imported as Sources (L0) + regenerated as L3 views. Pages stop being canonical. |

**Rationale:** SQLite-canonical gives trivial backup (one file), clean migrations, and
one-command index rebuilds. Kuzu (young, harder to back up) stays derived, so its
immaturity never risks data loss. Matches PER-317's "rebuildable indexes" requirement.

---

## 4. Canonical Knowledge Model (L1)

Source-to-knowledge lineage: `Source → Document → Chunk`, then knowledge objects
extracted from chunks.

### Evidence lineage

- **Source** — a content-addressed, versioned ingested item (document, web page,
  conversation, repo snapshot, message, media, test run, deployment). Fields:
  `id`, `content_hash`, `version`, `source_type`, `origin_uri`, `ingested_at`, `scope`.
- **Document** — a normalized/parsed form of a Source (extracted text, structure).
  Fields: `id`, `source_id`, `mime`, `normalized_hash`.
- **Chunk** — an addressable span of a Document used as an evidence anchor.
  Fields: `id`, `document_id`, `span` (offset/line range), `text_hash`.

### Knowledge objects

- **Entity** — a resolved thing: person, org, concept, code symbol, project, place.
- **Artifact** — a concrete produced object: file, repo, commit, PR, test, deployment,
  message thread. (Distinguished from Entity: artifacts are things that *exist*; entities
  are things referred to.)
- **Event** — something that happened at a time: a meeting, a deploy, a decision, a commit.
- **Claim** — an asserted fact ("Alice leads project X"), the unit of contestable knowledge.
- **Relationship** — a typed directed edge between any two of the above.

### Cross-cutting metadata (on every knowledge object)

- **Provenance** — ≥1 evidence link (`chunk_id` + span) and `extraction_method`.
  `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}` (adopted from graphify):
  - `EXTRACTED` — directly stated in a source (import statement, explicit sentence).
  - `INFERRED` — derived by cross-file/cross-source resolution.
  - `AMBIGUOUS` — conflicting or low-confidence signals; flagged for review.
- **Confidence** — numeric score + producing agent/parser identity.
- **Temporal validity** — bitemporal: `valid_from` / `valid_to` (when the fact was true
  in the world) and `recorded_at` (when Archivum learned it).
- **Scope** — partition + access label (`personal`, `work`, `repo:archivum`, …). Applied
  to every object; enforced at query time.
- **Supersession** — explicit `supersedes` / `superseded_by` edges. Contradictions are
  modeled, never silently overwritten. Newer high-confidence claims supersede older ones;
  both remain queryable with their temporal validity.

### Invariant

Every L1 knowledge object carries ≥1 provenance link, a confidence score, and an
extraction method. An object with no evidence cannot exist in L1.

---

## 5. Extraction Engine (hybrid, source-type routed)

Ingestion runs a **deterministic stage** always; an **agent-worker stage** only for
sources that need natural-language judgment. Routing by source type:

| Source type | Extractor | LLM? | Retrieval path (L2) |
|-------------|-----------|------|---------------------|
| Code / repositories | tree-sitter AST (**Archgraph**, §7) | No | graph + lexical |
| Docs / PDFs / conversations | agent workers (PTY + skills) | Yes | vector + graph |
| Structured (schemas, manifests, calendar, email headers) | deterministic parsers | No | graph + lexical |

### Deterministic stage

`ingest → content-address (L0) → parse/normalize (Document) → chunk → embed → keyword index`.
Reproducible and cheap. For code, this stage also produces the full code graph via
tree-sitter — **no LLM touches code**. For structured data, deterministic parsers emit
entities/edges directly.

### Agent-worker stage

PTY-hosted agent workers, each equipped with indexing/sorting skills, pull a work queue,
read normalized Documents, and emit candidate `Entity` / `Claim` / `Event` /
`Relationship` objects — each with an evidence span and confidence. Workers also resolve
contradictions (emit supersession edges). All writes pass through a **validation layer**
(schema + invariant checks from §4) before landing in L1.

**Each agent session is itself captured as a Source** (its user-visible activity and tool
calls), giving full provenance and feeding PER-316. Hidden model reasoning is not stored.

### Caching (incremental updates)

- **AST cache** keyed by file content hash, versioned by extractor version.
- **Semantic cache** keyed by a fingerprint of the extraction prompt — survives version
  bumps, so unchanged sources are never re-billed to an LLM.
- `--update` re-extracts only changed sources; dangling edges (to deleted sources) are
  pruned on the next pass.

---

## 6. Trust Invariants

1. Evidence (L0) is immutable and never mutated by generated knowledge.
2. Every L1 knowledge object cites ≥1 piece of evidence.
3. Confidence and extraction method are always recorded.
4. Contradictions are modeled via supersession, never overwritten.
5. Retrieval must surface **"insufficient evidence"** rather than fabricate certainty
   (enforced in PER-319).
6. Any L2 index or L3 view can be deleted and regenerated from L1 without data loss.

---

## 7. Archgraph — Developer Intelligence Subsystem

Archgraph is the **code-typed slice of the unified graph**, not a separate store. It
consists of:

- **Deterministic extractor.** A graphify-style tree-sitter AST walk (36+ languages),
  running in the deterministic stage with zero LLM cost. Emits code-typed L1 objects:
  - `Entity`: symbol, module, type, package.
  - `Artifact`: file, repo, commit, PR, test, deployment.
  - `Relationship`: `calls`, `imports`, `inherits`, `depends_on`, `references`, each with
    an `EXTRACTED | INFERRED | AMBIGUOUS` method.
- **Cross-repository resolver.** Entity resolution in L1 links the same symbol/package
  across repositories and commits. (graphify is repo-scoped; cross-repo resolution is the
  first Archivum differentiator.)
- **Evidence bridging.** Because code, conversations, decisions, PRs, and deployments all
  land in the same L1 store, Archgraph edges connect a code symbol to the conversation
  that decided it, the PR that shipped it, and the deploy/incident that followed. (The
  second differentiator; a standalone code-graph tool cannot cross this boundary.)

**Retrieval for code** does not use vectors: deterministic graph traversal + lexical
(trigram/IDF-style) scoring, per graphify's finding that this beats dense RAG on code.
Vectors (Qdrant) remain for natural-language sources only.

---

## 8. Retrieval & Context Packages (feeds PER-319)

The primary agent-facing output is a **scoped context package**, not raw files or a full
corpus dump — this is the core token-efficiency decision:

- A query seeds 2–3 entry nodes, expands a bounded neighborhood (BFS, depth-limited,
  relation-filtered), and returns ~5–10 nodes with their edges, each annotated with
  source citation, extraction method, and confidence.
- Hybrid retrieval fuses source/keyword (FTS), vector (Qdrant, natural-language only),
  graph (Kuzu), and temporal filters.
- The agent reads the subgraph, not the underlying documents; confidence labels tell it
  when to fetch full evidence. Answers cite evidence or declare it insufficient.

---

## 9. Migration From Current Repo

1. Keep FastAPI, SQLite, Qdrant, Kuzu, Caddy, MCP.
2. **Add** the content-addressed blob store (L0).
3. Reshape the SQLite schema to the L1 model (§4).
4. Import existing `wiki_data` markdown as Sources (L0 evidence); regenerate as L3 views.
   Markdown pages stop being canonical.
5. Refit the current ingest pipeline into the deterministic stage; add the agent-worker
   queue + validation layer.
6. Add the Archgraph tree-sitter extractor as a deterministic-stage producer.
7. Re-point MCP tools at L1 / the retrieval layer (context packages), not markdown files.

---

## 10. What This Replaces

- **Markdown-first:** pages demoted to L3 generated views; canonical truth moves to L0+L1.
- **Separate Archgraph:** folded in as the code-typed slice of the unified graph.

## 11. Deferred / Future

- **Reflection sidecar** — a session-scoped work-memory layer tracking useful vs.
  dead-end queries with half-life decay (graphify's `reflect.py` pattern). Orthogonal to
  canonical knowledge; kept out of L1. Revisit after retrieval (PER-319) lands.
- Perceo Suite integration surfaces.
