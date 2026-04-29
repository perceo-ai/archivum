# Graph Model (Kuzu)

Archivum stores the knowledge graph in an embedded **Kuzu** database (used by the graph UI and graph neighbor APIs).

## Node types

- `Page`
  - Key: `slug` (string)
  - Properties: `title`, `wiki_id`
- `Entity`
  - Key: `name` (string)
  - Properties: `type`, `wiki_id`

## Edge types (what auto-connects)

- `Page -[:REFERENCES]-> Page`
  - Source: `[[wikilink]]` syntax inside page markdown content.
  - Behavior: only created when the target page exists (slug found in SQLite during ingest).

- `Page -[:MENTIONS]-> Entity`
  - Source: case-insensitive substring match of extracted `Entity.name` inside the page markdown content.
  - Behavior: no positions/offsets are stored; it’s a simple containment check.

- `Entity -[:RELATED_TO]-> Entity`
  - Source: Claude-provided `relationships[]` JSON from the extraction step.
  - Behavior: inferred purely from the LLM output; no extra verification pass exists.

## Rebuild / consistency

If you change page content or ingest order affects `REFERENCES` edge creation, you can rebuild derived edges:

- `POST /api/rebuild-indexes`
  - Re-initializes derived stores (Qdrant + Kuzu `Page` nodes).
  - Rebuilds `REFERENCES` edges by scanning `[[wikilink]]` in each page’s stored content.

