# Archivum Release Progress

_Last updated: 2026-07-12_

## Target

Ship Archivum as a self-hosted, server-hosted Obsidian-style second brain:

- Markdown wiki with folders, backlinks, wikilinks, search, graph, ingest, query, sharing, and export.
- MCP server for agents to read, search, query, ingest, and write the wiki.
- Docker Compose install path that boots from a clean checkout after `.env` setup.
- Honest open-source docs with no private project artifacts or unverified launch claims.

## Current Status

| Area | Status | Evidence |
|---|---|---|
| Repo cleanup | Verified | PER-198 moved to In Review after removing private planning artifacts and committed generated clutter. |
| License | Verified | `LICENSE` and package metadata use Apache-2.0. |
| README positioning | Verified | PER-218 ready for review; README now positions Archivum as a server-hosted Obsidian-style second brain. |
| Progress docs | Verified | PER-219 ready for review; stale "feature complete" claims replaced with verified/partial/unknown status. |
| Docker clean boot | Verified | PER-216 ready for review; `docker compose down && docker compose up -d --build` boots backend, frontend, MCP, Qdrant, Ollama, and Caddy. |
| Ingest to query loop | Verified | PER-217 ready for review; markdown source ingested, appeared in search, and query returned source citation plus answer marker. |
| Backend test suite | Verified | Clean container copy ran `uv run --group dev pytest /tmp/workspace/tests -q`: 258 passed. |
| Frontend test/build | Verified | `npm test --workspace apps/frontend` passed 29 tests; `npm run build --workspace apps/frontend` completed. |

## Build Next

1. Review PER-216, PER-217, PER-218, and PER-219.
2. Move PER-214 and PER-215 through review/closure if the verification-only result is enough.
3. Continue PER-220 to PER-224 for the browser second-brain UX.

## Notes

- Treat old checkmarks as implementation evidence only, not release proof.
- Mark features "Verified" only when backed by a command, test, or manual smoke result.
- Keep Archductor/Archgraph-specific language out of public Archivum docs unless it is clearly an integration note.
