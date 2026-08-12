# Graph Model

Markdown pages are the human editing surface. Canonical knowledge rows preserve the owner profile, page-authored content, projects, thoughts, extracted entities, relationships, citations, confidence, and extraction method. Qdrant, Kuzu, FTS, and code lexical indexes are rebuildable projections. Retrieval defaults to `person:self` when the caller does not provide another seed.

Archivum stores the graph projection in embedded Kuzu. The graph powers graph APIs, graph UI, and MCP neighbor lookups, while canonical rows remain the source for rebuilding and cited context.

## Owner-Centered Nodes

The canonical graph starts at `person:self`, the owner profile. Page-authored content links the owner to projects and thoughts, and extracted entities and relationships extend the graph to people, code, sources, and decisions.

## Node Types

| Node | Key | Properties |
|---|---|---|
| `Page` | `slug` | `title`, `wiki_id` |
| `Entity` | `name` | `type`, `wiki_id` |

## Edge Types

| Edge | Source | Notes |
|---|---|---|
| `Page -[:REFERENCES]-> Page` | `[[wikilink]]` syntax | Created only when the target page exists at edge-build time |
| `Page -[:MENTIONS]-> Entity` | Extracted entity names in page markdown | Case-insensitive substring match |
| `Entity -[:RELATED_TO]-> Entity` | Extraction LLM `relationships[]` | No separate verification pass |

## Rebuild

Use rebuild when content changes outside the normal write path or when ingest order left missing `REFERENCES` edges:

```bash
node packages/archivum-cli/src/index.js wiki rebuild-indexes
```

Rebuild reinitializes the derived Qdrant, Kuzu, FTS, and code lexical projections from canonical knowledge and editable markdown content.
