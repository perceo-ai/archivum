# Ingest Pipeline

Archivum ingests any supported source (file or URL) through a single orchestration pipeline. The important outcome is that ingest writes:

1. Canonical wiki markdown pages (disk + SQLite)
2. Semantic search vectors (Qdrant)
3. The graph model + edges (Kuzu)

## Flow (high level)

1. **Parse**
   - `backend/archivum/ingest/parsers.py` extracts cleaned text + metadata into a `ParsedDoc`.
2. **LLM extraction**
   - `backend/archivum/ingest/agent.py` calls Claude to produce:
     - `pages[]` (slug/title/content/tags)
     - `entities[]` (name/type)
     - `relationships[]` (from/to/type)
3. **Persist pages**
   - `backend/archivum/ingest/pipeline.py` writes markdown to the wiki directory.
   - `backend/archivum/db/sqlite.py` upserts into the `pages` table.
   - `backend/archivum/db/qdrant_client.py` chunks + embeds the page content and upserts vectors.
   - `backend/archivum/db/graph.py` upserts `(:Page {slug})`.
4. **Persist entities + entity relationships**
   - Entities are upserted as `(:Entity {name})`.
   - Claude-provided relationships become `(:Entity)-[:RELATED_TO]->(:Entity)` edges.
5. **Wire edges from page content**
   - `[[wikilink]]` targets become `(:Page)-[:REFERENCES]->(:Page)` edges.
   - Mentions of extracted entity names inside page content become `(:Page)-[:MENTIONS]->(:Entity)` edges.
6. **Finish**
   - The ingest log is updated in SQLite.

## Where “auto-connected edges” come from

### RELATED_TO (Entity ↔ Entity)
Created from the LLM JSON `relationships[]`.

### REFERENCES (Page ↔ Page)
Created by scanning each generated page’s markdown content for `[[wikilink]]` syntax.

### MENTIONS (Page ↔ Entity)
Created by a case-insensitive substring match of entity names inside the generated page content.

## Key limitation to know

`REFERENCES` edges are only created if the target page exists (by slug lookup in SQLite) at ingest time. If a page doesn’t exist yet, ingest won’t create the edge until you run a rebuild step (see `POST /api/rebuild-indexes`).

