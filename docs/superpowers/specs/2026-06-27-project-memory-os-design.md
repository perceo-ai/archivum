# Project Memory OS

Date: 2026-06-27
Status: Proposed and user-approved in chat

## Goal

Refocus Archivum into a hybrid project memory operating system built on top of an LLM-maintained wiki.

The product should follow the Karpathy-style separation of layers:

- immutable raw sources
- compiled wiki pages
- graph relationships
- vector retrieval
- MCP access for coding agents

This is not a generic life dashboard. It is a project-centered knowledge system for humans, Codex, and Claude Code to read from and write to safely.

## Customer Impact

- Gives the user one durable place to store and evolve project knowledge.
- Lets coding agents contribute useful context without silently rewriting history.
- Makes repository and product context easier to retrieve during implementation, debugging, and planning.
- Replaces the current fragmented UI with a project-centered workflow that matches the actual product value.

## Scope

In scope:

- Reframe Archivum around `project/repo` as the primary boundary
- Add immutable source records with provenance
- Treat wiki pages as compiled artifacts derived from sources
- Upgrade retrieval toward GraphRAG using graph expansion plus vector search
- Make MCP tools project-aware with read tools and narrow write actions
- Rebuild the frontend information architecture around project memory workflows
- Expand linting to detect stale, weakly grounded, or unlinked knowledge

Out of scope for the first implementation milestone:

- Broad autonomous agent orchestration
- Deep personal life-management workflows
- Full task automation beyond lightweight project follow-up records
- Large multi-user collaboration features
- Infrastructure changes not required for the project memory core

## Product Frame

Archivum should behave like a maintained project memory system, not a disconnected set of utilities.

### Core principle

The durable system is:

`raw sources -> compiled pages -> graph -> retrieval -> MCP/UI access`

Raw sources remain authoritative and append-only. Compiled pages are the living synthesis layer. Graph and vector retrieval exist to help humans and agents navigate and answer questions against that memory.

### Top-level product model

`Project` is the primary unit of organization.

Each project owns:

- sources
- compiled pages
- graph neighborhood
- retrieval scope
- MCP context
- operational views such as decisions, tasks, and activity

Cross-project links are allowed, but every artifact has one primary project.

## Data Model

### Projects

Projects are the top-level containers for project memory.

Required fields:

- `key`
- `name`
- `summary`
- `status`

Preferred additional fields:

- `repo_url`
- `local_path`
- `default_branch`

Each project should also have a canonical compiled project page that serves as the human-readable landing page.

### Sources

Sources are immutable evidence records.

Supported source types:

- `file`
- `url`
- `repo_snapshot`
- `agent_note`
- `meeting_note`
- `decision_note`

Required source metadata:

- `project_key`
- `source_type`
- `source_uri` or storage path
- `content_hash`
- `captured_at`
- `author`
- `source_ref`
- `ingest_status`

Key rule:

Agents do not edit old sources. They append new sources. This keeps the historical trail authoritative and avoids mutating evidence that has already been indexed and cited.

### Pages

Pages are compiled knowledge artifacts.

Examples:

- project overview
- current state
- architecture
- subsystem documentation
- onboarding
- release notes
- bug history

Pages may be generated or updated from new evidence, but they must preserve provenance. Every compiled page should expose which sources informed it and when it was last refreshed.

### Decisions

Decisions are not a separate truth system.

A decision should be stored as:

- a typed immutable source record
- a linked compiled page or compiled project page section

This preserves append-only history while still giving the user a clean narrative view.

### Tasks

Tasks may remain as structured records, but they are subordinate to project memory rather than the center of the product.

Each task should be attachable to:

- a project
- an optional page
- an optional source

Tasks exist to drive follow-up work from knowledge gaps, lint findings, or agent discoveries.

### Activity

Activity is an audit trail, not a destination feature.

It should show:

- ingests
- source appends
- page recompiles
- agent writes
- query runs
- lint runs
- MCP actions

This is essential for trust and debugging.

## Architecture

### Layer separation

Archivum should preserve three distinct knowledge layers:

1. raw sources
2. compiled wiki pages
3. retrieval materializations such as graph edges and vector chunks

The current repository already has ingest, pages, graph, vector search, and MCP support. The first major architectural change is to insert a durable source/provenance layer between ingest transport and compiled pages.

### Raw layer

Every ingest creates a source record first.

The source record stores the immutable evidence and metadata. Source content should live in raw storage separate from compiled page markdown.

### Compiled layer

Compilation is the job of the model.

Compilation behavior should support:

- `create page`
- `update page`
- `link page`
- `flag ambiguity`

The model should not merely dump per-source notes. It should maintain coherent compiled pages at the project and subsystem level.

### Retrieval layer

Retrieval should use both vector and graph structures.

The current query implementation is mostly vector-hit synthesis. The new target is GraphRAG:

1. resolve project scope
2. retrieve top semantic candidates from compiled pages and sources
3. expand graph neighbors from top pages, entities, and the project node
4. rank merged context
5. synthesize with citations and contradiction awareness

### Trust model

Users should be able to inspect:

- which sources informed a page or answer
- when those sources were added
- whether the page is stale
- whether contradictory evidence exists

Trust and inspectability matter more than hiding the system behind a chat box.

## Graph Model

Recommended node types:

- `project`
- `page`
- `source`
- `entity`

Recommended edge types:

- `HAS_SOURCE`
- `HAS_PAGE`
- `DERIVED_FROM`
- `REFERENCES`
- `MENTIONS`
- `RELATES_TO`
- `SUPERSEDES`

The most important new edge is `DERIVED_FROM`, which explicitly ties compiled pages back to the source records that informed them.

## Vector Strategy

Index both:

- compiled page chunks
- source chunks

Every chunk should include metadata for:

- `project_key`
- `layer`
- `source_type`
- `page_slug` or `source_id`

Default ranking should prefer compiled pages first and then raw evidence, so answers are concise but still grounded by authoritative underlying records.

## MCP Model

Archivum should serve as a project memory MCP for coding agents.

### Read tools

Initial project-aware read tools should include:

- `list_projects`
- `get_project`
- `search_project_memory`
- `get_page`
- `get_sources`
- `graph_neighbors`
- `query_project`

### Narrow write tools

Initial write behavior should be broad in access but narrow in mutation shape.

Recommended write tools:

- `append_source`
- `register_project`
- `create_task`
- `record_decision_note`
- `request_recompile`
- `write_page` for the compiled layer only

Key rule:

Agents can add evidence and update compiled artifacts, but they should not silently rewrite raw historical sources.

## Frontend Product Shape

The UI should become project-centered.

Recommended top-level navigation:

- `Projects`
- `Sources`
- `Wiki`
- `Graph`
- `Ask`
- `Lint`
- `Activity`

`Tasks` and `Decisions` should appear inside project context instead of living as global peer products.

### Main shell rules

- The first screen should orient the user around projects, not miscellaneous utilities.
- Each project should have a clear home showing current state, important pages, source activity, open follow-ups, and trust indicators.
- Source history and page provenance should be visible in the interface.
- Graph and query flows should respect project scope by default.

## Repo-Specific Changes

### Preserve

- existing wiki page CRUD
- ingest transport and progress events
- graph store
- vector search foundation
- MCP server shell
- auth and sharing foundations
- useful structured records from `life_os` where they support project memory

### Change hard

- make project scope first-class instead of assuming `wiki_id=default`
- add a persistent source model and raw source storage path
- treat compiled pages as derived artifacts with provenance
- reframe `life_os` views into project memory views
- upgrade query to GraphRAG
- make MCP writes safer and more project-aware

## First Shipping Milestone

Milestone name:

`Project Memory Core`

Includes:

- project model as the primary scope
- immutable source records
- compiled page provenance
- project-centric UI shell
- project-aware MCP read tools plus narrow writes
- GraphRAG query v1
- expanded linting for stale and unlinked knowledge

Does not include yet:

- advanced autonomous agents
- deep task automation
- broad life-management surfaces
- speculative enterprise abstractions

## Recommended Delivery Phases

1. Reframe the product
   - Rework frontend information architecture around projects
   - Demote or remove off-vision global pages from the main flow
   - Create project home and project-scoped navigation

2. Add source and provenance layer
   - Introduce source records
   - Persist raw storage references
   - Add `DERIVED_FROM` lineage
   - Make ingest write source first

3. Upgrade retrieval
   - Add project-scoped search and query
   - Blend compiled page hits, source hits, and graph neighbors
   - Surface contradiction and freshness signals

4. Upgrade MCP
   - Add project-aware read tools
   - Add source-append and recompile-oriented writes
   - Keep `write_page` as a compile-layer tool, not a history-editing tool

5. Add trust and maintenance loops
   - Expand linting
   - Show provenance in the UI
   - Improve activity and audit views

## Verification Bar

Before calling this transformation done:

- verify project-scoped ingest, search, query, graph, and MCP flows
- verify raw sources remain immutable in product behavior
- verify compiled pages expose provenance and freshness
- verify GraphRAG returns grounded answers with citations
- verify frontend navigation is project-centered rather than tool-centered
- run relevant tests, typecheck, lint, and build checks available in the repo

Success means:

- Archivum behaves like a durable project memory system
- coding agents can safely contribute context through MCP
- the wiki remains a maintained compiled artifact instead of a pile of disconnected notes
- project knowledge is easier to inspect, trust, and evolve over time
