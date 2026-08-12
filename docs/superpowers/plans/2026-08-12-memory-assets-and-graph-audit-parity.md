# Memory Assets and Graph Audit Parity Implementation Plan

**Goal:** Close the remaining gaps between Archivum and (a) TencentDB Agent Memory's *memory-as-governed-asset* model and (b) Graphify's *graph-native audit and discovery* model, without adding recurring LLM cost.

**Non-goals:** Replacing markdown as the human editing surface; replacing the canonical `person:self` knowledge store; adding new infrastructure dependencies.

## Gap Summary

| Principle | Source | Before | After |
|---|---|---|---|
| Typed memory assets with owner/version/status/visibility | Tencent | Missing | `memory_assets` + versions + canonical projection |
| L0→L1→L2→L3 memory layering | Tencent | L0/L1 evidence only | Deterministic distillation into atoms, scenarios, persona |
| Skill memory from real tool steps | Tencent | Missing | `extract_skill` gated on actual tool calls + outcome |
| Agent loadouts (who gets what memory) | Tencent | Missing | Agent profiles + bindings + resolved loadout package |
| Community / lobe discovery | Graphify | Missing | Deterministic greedy modularity over canonical graph |
| Shortest path + surprising links | Graphify | Missing | BFS path + surprise scoring with plain-language reasons |
| Plain-language graph audit | Graphify | Missing | `GraphReport` with narrative, provenance breakdown, gaps |

## Cost Discipline

Every new pipeline is **deterministic and LLM-free by default**:

- Atom extraction is regex/rule based over user-visible turns; each atom carries the exact quote it came from.
- Scenario and persona summaries are assembled from atoms, not generated.
- Skill steps come from recorded tool calls, never from prose inference.
- Community detection, shortest path, and surprise scoring are pure graph algorithms. Label propagation was tried first and rejected: on a bridged graph with unique seed labels it collapses every lobe into one community, so greedy modularity is used instead.

LLM enrichment stays optional and is never required for parity.

## Architecture

```
L0  blobs (content-addressed conversation bytes)          [existing]
L1  sources → documents → chunks                          [existing]
L1' memory atoms      kind=memory_atom      layer=L1      [new]
L2  scenario memory   kind=memory_scenario  layer=L2      [new]
L3  persona memory    kind=memory_persona   layer=L3      [new]
--- all of the above are addressable as typed memory assets ---
```

Assets are rows in `memory_assets`, versioned in `memory_asset_versions`, projected into the canonical knowledge store as `KnowledgeObject`s owned by `person:self`, and optionally backed by an editable markdown page.

## File Structure

```
apps/backend/archivum/memory/
    models.py      typed asset / agent / binding / layer models
    schema.py      MEMORY_SCHEMA SQL (idempotent)
    registry.py    MemoryAssetRegistry: register, version, status, bindings
    atoms.py       deterministic L1 atom extraction from a Conversation
    skills.py      deterministic skill extraction gated on real tool calls
    distill.py     L1 → L2 → L3 assembly (pure, no DB)
    loadouts.py    agent loadout resolution
    service.py     DB + canonical projection + markdown page orchestration
apps/backend/archivum/knowledge/graph_audit.py   communities, paths, surprise, report
apps/backend/archivum/api/memory.py              REST surface
apps/backend/archivum/api/graph.py               + audit routes
apps/frontend/src/pages/MemoryPage.tsx
apps/frontend/src/components/GraphAuditPanel.tsx
```

## Tasks

- [x] Task 1 — Memory asset registry (schema, registry, canonical projection, owner rel types)
- [x] Task 2 — Deterministic atom extraction (`atoms.py`) with quote-anchored citations
- [x] Task 3 — Layer assembly (`distill.py`): atoms → scenario → persona, thresholded
- [x] Task 4 — Skill memory (`skills.py`) gated on ≥N real tool calls plus an outcome
- [x] Task 5 — Agent profiles, bindings, and loadout resolution
- [x] Task 6 — Service layer: distill a captured conversation end to end, review-gated
- [x] Task 7 — Graph audit: communities, shortest path, surprising links, report narrative
- [x] Task 8 — REST routes (`/api/memory/*`, `/api/graph/audit|communities|path|surprising`)
- [x] Task 9 — MCP tools for assets, loadouts, distillation, skills, graph audit
- [x] Task 10 — Frontend memory + graph audit surfaces
- [x] Task 11 — Tests across memory, graph audit, API, MCP, frontend
- [x] Task 12 — Docs: architecture page, docs map, README, progress

## Parity Definition

Parity is reached when:

1. Every memory kind (wiki page, chat memory, skill, code graph, source bundle, scenario, persona) is a typed asset with owner, scope, status, visibility, and version history.
2. A captured conversation can be distilled into cited L1 atoms, an L2 scenario, and an L3 persona update — with anything below the confidence threshold routed to human review instead of written silently.
3. A completed agent session with real tool calls yields a reusable skill asset with steps, validation, and citations.
4. An agent can be equipped with a named loadout and receive only the bound assets, cited.
5. The canonical graph can be audited: communities, shortest paths, surprising cross-community links, and a plain-language report of provenance and gaps.
6. Everything above runs without any LLM call.
