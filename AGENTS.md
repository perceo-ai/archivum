# Archivum Agent Instructions

## Project Context

Archivum work lives in the Linear `Archivum` project.

When pulling work from Linear in this repository:

- Query the `Archivum` project specifically.
- Be specific with Linear queries: project, status, assignee, issue key, labels, and relevant text.
- When starting a Linear task, move it to `In Progress`.
- When finishing a Linear task, move it to `In Review` so the user can review and push.

## Product Direction

Archivum is a self-hosted, server-hosted Obsidian-style second brain.

Keep public-facing docs and work focused on:

- Markdown wiki and vault navigation
- Backlinks and wikilinks
- File and URL ingest
- Search, query, graph, sharing, and export
- MCP access for agents
- Docker Compose self-hosting

Do not describe Archivum as Archductor, Archgraph, project memory, or generic GraphRAG work unless it is clearly a private integration note.

## Agent Source of Truth

Read these before making product/docs changes:

- `README.md` for customer-facing install/product docs.
- `docs/README.md` for the docs map.
- `docs/agent-guide.md` for coding-agent orientation.
- `docs/project/progress.md` for verified/partial/unknown status.
- `.env.example`, `docker-compose.yml`, and `docker-compose.images.yml` for runtime truth.

Old PRD, operator handoff, and root `Progress.md` docs were intentionally pruned. Do not recreate them unless the user explicitly asks.

## Verification

Run the relevant checks before claiming completion:

```bash
npm test --workspace apps/frontend
npm run build --workspace apps/frontend
npm test --workspace packages/archivum-cli
cd apps/backend && uv run --group dev pytest ../../tests -q
```

For docs-only changes, also scan for stale language:

```bash
rg -n "scripts/[b]ootstrap|[N]eo4j|[y]ou@youremail|[L]ast updated: 2026-06|[f]eature complete" -g "*.md" -g "!node_modules/**" -g "!apps/backend/.venv/**"
```
