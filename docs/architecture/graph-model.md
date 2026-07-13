# Graph Model

Archivum stores graph data in embedded Kuzu. The graph powers graph APIs, graph UI, and MCP neighbor lookups.

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

Rebuild reinitializes derived Qdrant and Kuzu data from canonical wiki content and SQLite metadata.
