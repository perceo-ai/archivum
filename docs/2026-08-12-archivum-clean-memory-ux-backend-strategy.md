---
title: "Archivum Clean Memory UX and Backend Strategy"
strategy_date: "2026-08-12"
last_reviewed: "2026-08-12"
status: "working strategy"
related_docs:
  - "docs/2026-08-12-perceo-suite-ux-strategy.md"
  - "docs/repo-summaries/2026-08-12-archivum-summary.md"
---

# Archivum Clean Memory UX and Backend Strategy - 2026-08-12

## Purpose

This document defines the emerging Archivum product strategy around the goal: **it keeps my knowledge clean**.

Archivum should become a human-centered context and memory system. It is not just an Obsidian-like markdown wiki, and it is not just GraphRAG over files. It should let a human capture broadly, then aggressively evaluate, prune, compress, scope, and promote only the most useful knowledge into long-term memory for humans and agents.

The long-term suite-level win is: **my coding agents work better because they know me and my context**.

The near-term Archivum win is: **I can chat naturally, capture what I mean, and the system keeps durable memory succinct instead of hoarding noise**.

## Core Thesis

Archivum revolves around a singular human node: `person:self`.

Projects, repositories, docs, sources, topics, interests, people, memories, graph relationships, and agent context all orbit that human. A project can be a strong lens, especially inside the Perceo suite, but it is not the root of the product.

The backend and UX should follow one rule:

**Raw capture can be abundant. Agent-usable long-term memory must be scarce.**

That means the evaluator/pruner is a core product primitive, not a cleanup job. Archivum should ingest and preserve enough raw material for provenance and reprocessing, but it should only promote high-signal, reviewed, scoped memory into the layer that agents can load.

## Product Identity

Archivum should be a **chat-first, context-visible memory librarian for the human**.

The user should not feel like they are administering a graph database or maintaining a folder hierarchy. They should feel like they are chatting with a memory librarian that captures, organizes, prunes, and prepares context for future work.

The chat agent should be good at:

- Remembering a thought succinctly.
- Explaining what it saved and why.
- Saying what it refused to save because it was noisy or redundant.
- Preparing context for coding agents.
- Finding prior decisions, preferences, interests, and project knowledge.
- Showing provenance for claims.
- Proposing memory, graph, or doc updates as reviewable suggestions.
- Respecting "do not remember that."

It should not become a generic assistant. It can answer questions, but its product role is memory, context, retrieval, pruning, provenance, and agent preparation.

## UX Principles

- **Human-first**: the home experience starts from the human's active context, not from folders, repos, or a global graph.
- **Chat-first**: creation and retrieval should feel conversational and low-friction.
- **Context-visible**: chat cannot be the only surface; durable changes must be inspectable and correctable.
- **Capture broadly, promote narrowly**: raw capture is easy; trusted memory is gated.
- **Docs for humans, memory for agents**: human docs can be expressive; agent memory should be extracted, compressed, reviewed, and scoped.
- **Graph as reviewable intelligence**: graph structure is derived and reviewable, not a manually maintained canvas.
- **Review without chores**: suggested updates should feel lightweight, not like an administrative inbox.
- **Provenance survives simplification**: pruning should reduce working memory size, not erase where knowledge came from.

## Home UX

Archivum home should be a `person:self` dashboard with a prominent chat/capture composer and immediate active context.

The first screen should surface:

- Chat/capture composer.
- Current active context around the human.
- Recent captures.
- Suggested memory updates.
- Stale or conflicting memory warnings.
- Active topics, projects, interests, people, and repos.
- Quick ask/search.
- Recent accepted memory.

The home should not over-index on projects. Projects are one lens among many. Archivum also needs to handle personal interests, beliefs, preferences, research trails, relationships, product ideas, general knowledge, and loose thoughts that may never belong to a project.

## Navigation Model

Use a human-first dashboard with graph-backed lenses.

Primary navigation should be approachable:

- Home
- Topics
- Projects
- People
- Repos
- Sources
- Memory
- Graph
- Review

Internally, these can all be graph entities and relationships. Externally, the user should not need to think in graph primitives unless they choose to inspect the graph.

Avoid making "Spaces" the core model too early. Spaces risk recreating folder hierarchy with a different name. Lenses over a human-centered graph are more flexible and better aligned with the product.

## Creation Flow

Creation should be chat/capture first, not blank-page first.

The user should be able to say:

- "Remember that I want Archivum to be centered on the human, not projects."
- "Ingest this repo and tell me what matters."
- "Save this as a product direction note."
- "This is important for my agents."
- "This is just a rough thought, do not over-structure it."
- "Prune this meeting/session into durable memory."

Archivum can create or update docs, sources, candidate memory, and graph suggestions from that interaction, but durable promotion should be visible through suggested update cards.

Blank markdown pages should still exist for human writing. They are not the center of the first-run UX.

## Suggested Updates UX

When Archivum proposes changes to durable memory, graph, or docs, it should create lightweight suggested update cards.

Suggested update cards should support:

- Accept
- Edit then accept
- Reject
- Merge with existing
- Replace existing
- Keep both
- Retire stale memory
- Change scope
- Change visibility

Each card should show:

- Proposed memory/doc/graph update.
- Type.
- Scope.
- Source citations.
- Why the evaluator thinks it matters.
- Redundancy or conflict warnings.
- Estimated durability.
- Agent visibility.

Chat can surface important suggestions inline, but the suggested updates panel is the durable review interface. This keeps the product chat-first while making long-term changes inspectable.

## Trust Model

The trust model should be strict:

- Raw capture is automatic.
- Imported sources are searchable and inspectable.
- Candidate extraction is automatic.
- Durable memory promotion requires review.
- Graph changes that affect durable context require review.
- Agent-loadable memory is accepted, scoped, and budgeted.

Low-risk housekeeping can be automatic later, such as deduplicating exact duplicate captures, expiring stale candidates, refreshing embeddings, or linking a source to a high-confidence existing project. But durable meaning should not silently promote.

## Retention Model

Use tiered retention.

- Human-authored docs are durable.
- Imported source files/URLs preserve original provenance and are durable unless explicitly removed.
- Repository snapshots and code graph projections are rebuildable.
- Agent/session noise can expire unless pinned, cited, or promoted.
- Candidate memory can expire if rejected or ignored.
- Accepted memory persists with lifecycle history.
- Raw evidence behind important accepted memories should be retained or archived.

This prevents Archivum from becoming an infinite attic while preserving enough evidence to explain why it believes something.

## Docs, Sources, Memory, and Graph

Archivum needs a clean split between object types.

### Docs

Docs are for humans. They can be expressive, messy, long-form, and editable as markdown.

Docs can produce memory candidates, but the doc itself should not automatically become agent memory. The user should not be forced to write in an agent-optimized style.

### Sources

Sources are original inputs:

- Files
- URLs
- Repositories
- Chats
- Agent sessions
- Transcripts
- Screenshots or artifacts
- Imported documents

Sources preserve provenance. They can be parsed, indexed, summarized, graphified, and reprocessed.

### Memory

Memory is extracted from docs, sources, sessions, and conversations.

It should be:

- Typed.
- Scoped.
- Succinct.
- Reviewed.
- Versioned.
- Cited.
- Budgeted.
- Agent-visible only when accepted.

### Graph

The graph is derived and reviewable intelligence.

Humans should not primarily maintain the graph by hand. They should write, capture, ingest, and review. Archivum proposes graph structure; the human accepts, rejects, merges, or annotates. Direct graph edits should be rare corrections with provenance.

## Backend Architecture

The backend should be organized around layered stores and promotion gates.

### Raw Store

Append-only or source-preserving storage for captures, docs, URLs, files, repos, sessions, transcripts, and artifacts.

Purpose:

- Preserve input.
- Support reprocessing.
- Support provenance.
- Allow broad capture without trust pollution.

Raw store content is not automatically agent-loadable memory.

### Canonical Knowledge Store

Normalized records for claims, entities, relationships, decisions, preferences, project facts, repo facts, citations, confidence, extraction method, ownership, and provenance.

Purpose:

- Provide a structured intermediate layer.
- Support graph projection.
- Support conflict detection.
- Preserve traceable extracted knowledge before promotion.

Canonical knowledge can include provisional records.

### Candidate Store

Holds evaluator outputs waiting for review:

- Candidate memories.
- Candidate graph nodes/edges.
- Candidate doc updates.
- Candidate source summaries.
- Conflict cards.
- Merge/replacement proposals.

Candidates should have lifecycle state: proposed, accepted, edited, rejected, merged, replaced, expired, or retired.

### Memory Asset Store

The scarce, reviewed, agent-usable memory layer.

Accepted memory assets should be structured records with markdown bodies. Internally, they should not be plain markdown files only.

Each memory asset should include:

- ID.
- Type.
- Markdown body.
- Scopes.
- Source citations.
- Confidence.
- Human approval metadata.
- Lifecycle state.
- Version.
- Supersedes/superseded-by links.
- Conflict/merge lineage.
- Agent visibility.
- Created/updated/reviewed timestamps.

Optional export/import as markdown with YAML frontmatter is useful, but the filesystem format should not dictate the backend model too early.

### Graph Projection

Derived projection over canonical knowledge, memory assets, docs, sources, repos, and people.

The graph supports:

- Human-centered exploration.
- Topic/project/repo/person lenses.
- Relationship review.
- Retrieval neighborhoods.
- Context pack construction.
- Technical code graph overlays.

The graph should be rebuildable where possible and annotated where human review adds meaning.

### Context Pack Builder

Builds scoped context for agents or human workflows.

Inputs:

- Accepted memory.
- Relevant human docs.
- Source summaries.
- Graph neighborhoods.
- Repo/code insights.
- Current task.
- Agent permissions.
- Recency and staleness signals.

Output:

- Compact context bundle.
- Citations.
- Scope explanation.
- Exclusions when useful.
- Token/size budget compliance.

Archductor should consume context packs. Archivum should own long-lived context.

### Retention Engine

Applies lifecycle and budget rules:

- Expires stale candidates.
- Archives raw noise.
- Retires superseded memory.
- Flags stale memory.
- Enforces per-scope budgets.
- Preserves provenance for promoted knowledge.

Retention should be visible enough that the user trusts it, but not so visible that the product becomes a chore.

## Evaluator and Pruner Pipeline

The evaluator should be hybrid: deterministic skeleton, LLM-assisted semantic judgment.

LLMs alone will over-save eloquent junk. Deterministic rules alone will miss meaning. Archivum needs both.

Pipeline:

1. **Normalize**
   Parse sources and captures into chunks, metadata, entities, timestamps, and source references.

2. **Deterministic Filters**
   Drop junk, exact duplicates, low-content captures, expired run noise, oversized blobs, and unsupported artifacts.

3. **Candidate Synthesis**
   Use LLMs or local semantic extractors to propose candidate memories, claims, wiki updates, graph edges, source summaries, skills, and code insights.

4. **Scoring**
   Score candidates on human relevance, future utility, durability, specificity, novelty, evidence quality, compression ratio, and risk.

5. **Budget Enforcement**
   Enforce hard budgets per human, topic, project, and repo.

6. **Conflict Detection**
   Detect contradictions and overlap using exact keys, embeddings, graph neighborhoods, timestamps, source relationships, and memory lineage.

7. **Review Routing**
   Produce suggested update cards for accept, edit, reject, merge, replace, keep both, or retire.

8. **Promotion**
   Accepted candidates become memory assets or reviewed canonical knowledge.

9. **Retention**
   Raw and candidate data expire, archive, or persist based on tier and promotion state.

## Evaluator Optimization Target

The evaluator should optimize for **minimum high-signal memory**.

Memory candidates must justify their existence. A candidate should survive only if it is likely to be useful later to the human or to an agent acting on behalf of the human.

Primary scoring dimensions:

- **Human relevance**: does this matter to `person:self`?
- **Future utility**: will it improve a future human or agent session?
- **Durability**: will it remain true or useful?
- **Specificity**: is it concrete enough to act on?
- **Novelty**: is it not already captured?
- **Evidence quality**: is it cited and traceable?
- **Compression ratio**: can it replace many noisy details with one useful memory?
- **Risk**: could remembering this be harmful, sensitive, misleading, or stale?

## Memory Budgets

Memory budgets should be scoped by human, topic, project, and repo.

Initial scopes:

- `person:self`
- topic
- project
- repo

Every memory candidate should have proposed scopes. The evaluator should assign scopes automatically, but review cards must make scope visible and editable before acceptance.

Budget examples:

- Human profile: very small, durable, high-confidence.
- Topic memory: medium-sized and evolving.
- Project memory: concise decisions, principles, and active direction.
- Repo memory: architecture notes, test commands, invariants, and technical constraints.

Do not start with only a global memory budget. Global-only pruning is too crude for a human-centered system.

## Memory Asset Types

Use a small typed core with tags/scopes for nuance.

Initial memory types:

- `profile`: durable facts about the human or operating context.
- `preference`: how the human likes things done.
- `decision`: chosen direction with date/context.
- `principle`: durable rule or product/design belief.
- `fact`: concrete claim with provenance.
- `procedure`: repeatable workflow or instruction.
- `skill`: executable or agent-followable method extracted from successful work.
- `relationship`: connection between human/person/project/topic/org.
- `source_summary`: compressed summary of an imported source.
- `code_insight`: repo/module/API/test/architecture insight.

Avoid freeform untyped memory as the main model. Untyped memory is hard to prune, budget, score, retrieve, and conflict-check.

## Conflict Handling

Conflicts should create review candidates. Do not silently resolve non-trivial contradictions.

When a new candidate conflicts with accepted memory, Archivum should produce a card that lets the human:

- Replace old memory.
- Keep both with scope or time distinction.
- Merge into a corrected memory.
- Reject the new candidate.
- Retire the old memory.

Memory needs lineage:

- Created from source.
- Accepted by human.
- Superseded.
- Contradicted.
- Merged.
- Retired.
- Rejected.

This is required for trust. The system should be able to explain why it currently believes something.

## Technical Project Graphification

Technical graphification should be layered. The user-visible value is not the graph itself; it is better developer context for humans and agents.

Layers:

1. **Code Graph**
   Derived, rebuildable substrate. Files, symbols, imports, calls, dependencies, routes, API boundaries, tests, configs.

2. **Architecture Knowledge**
   Reviewed or high-confidence canonical knowledge. Modules, responsibilities, invariants, data flow, integration points, risk areas, test commands, design constraints.

3. **Developer Context Pack**
   Task-ready bundle generated on demand: what this repo is, where to change things, how to test, and what not to break.

The code graph is infrastructure. The product value is that agents understand the repo.

## Repo Ingestion Strategy

Use shallow-first ingestion, then deepen on intent.

Initial repo ingestion should produce:

- Repo identity.
- File tree.
- Language/package map.
- Key configs.
- Scripts and test commands.
- README/docs summary.
- Dependency/import overview.
- Module boundary guesses.
- Candidate architecture notes.

Deeper graphification should happen when:

- A human asks about a code area.
- Archductor starts a coding task.
- An agent needs a context pack.
- A PR/review touches relevant files.
- A module is repeatedly used.
- The evaluator identifies durable technical insight.

Avoid full deep graph extraction on every ingest. It is expensive, noisy, and conflicts with the clean-memory goal.

## Relationship to TencentDB Agent Memory and Graphify

TencentDB Agent Memory's asset framing maps well to Archivum:

- Chat Memory
- Skill
- LLM-Wiki
- Code-Graph

Archivum should learn from that shape but adapt it around the human, not the team or agent framework.

Archivum's rough mapping:

- Chat Memory -> reviewed human-centered memory assets.
- Skill -> reviewed procedures or executable agent methods.
- LLM-Wiki -> human docs plus source summaries and curated knowledge.
- Code-Graph -> technical graphification and repo context substrate.

Graphify should be treated as a candidate structure generator, not a permanent truth machine. It can turn docs, conversations, and repos into graph candidates, but the evaluator/pruner decides what survives into reviewed memory or canonical graph relationships.

## Context Pack Generation

Context packs are the bridge to Archductor and future agents.

A context pack should be generated from:

- Accepted memory only by default.
- Relevant human-authored docs.
- Reviewed source summaries.
- Scoped graph neighborhoods.
- Code insights and repo graph slices.
- Current task intent.
- Agent permissions.
- Token budget.

Context packs should include:

- What was included.
- Why it was included.
- Citations/provenance.
- What was excluded due to budget or trust.
- Staleness warnings.

The best long-term "wow" is when Archductor can launch an agent with a concise, trusted Archivum context pack and the agent performs noticeably better.

## Backend Object Sketch

### Memory Candidate

Fields:

- `id`
- `type`
- `body_markdown`
- `source_refs`
- `proposed_scopes`
- `confidence`
- `scores`
- `duplicates`
- `conflicts`
- `retention_tier`
- `agent_visibility`
- `review_state`
- `created_at`
- `expires_at`

### Memory Asset

Fields:

- `id`
- `type`
- `body_markdown`
- `scopes`
- `source_refs`
- `confidence`
- `approved_by`
- `reviewed_at`
- `version`
- `status`
- `supersedes`
- `superseded_by`
- `agent_visibility`
- `created_at`
- `updated_at`

### Scope

Fields:

- `id`
- `type`: human, topic, project, repo, person, org
- `name`
- `parent_scope_id`
- `budget`
- `retention_policy`

### Source

Fields:

- `id`
- `type`
- `uri_or_path`
- `checksum`
- `metadata`
- `ingestion_state`
- `last_ingested_at`
- `provenance_policy`
- `retention_tier`

### Graph Proposal

Fields:

- `id`
- `source_refs`
- `subject`
- `predicate`
- `object`
- `confidence`
- `proposed_scopes`
- `review_state`
- `conflicts`

## Open Backend Questions

- What are the first hard memory budgets for `person:self`, topic, project, and repo?
- How much raw data should be retained by default before archive or expiry?
- Should accepted memories be stored in SQLite first, then projected to files, or should file export be implemented from the beginning?
- Which evaluator components must work without external model APIs?
- How should sensitive personal memory be classified and excluded from default agent context packs?
- What is the minimum useful repo graph for the first Archductor integration?
- How should user feedback from agent performance later influence memory pruning?

## Working Recommendation

Build Archivum around the lifecycle:

1. Capture broadly through chat, docs, imports, repo ingestion, and agent sessions.
2. Preserve sources and provenance.
3. Extract candidates through a hybrid evaluator.
4. Score and prune aggressively.
5. Route durable meaning through suggested update cards.
6. Promote only reviewed, scoped, succinct memory.
7. Maintain graph projections as reviewable intelligence.
8. Build agent context packs from accepted memory and relevant source-backed context.

This gives Archivum the UX of a helpful memory librarian and the backend discipline of a clean, sparse, human-centered long-term memory system.

