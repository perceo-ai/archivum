# Graph Model

Markdown pages are the human editing surface. Canonical knowledge rows preserve the owner profile, page-authored content, projects, thoughts, extracted entities, relationships, citations, confidence, and extraction method. Qdrant, Kuzu, FTS, and code lexical indexes are rebuildable projections. Retrieval defaults to `person:self` when the caller does not provide another seed.

Archivum stores the graph projection in embedded Kuzu. The graph powers graph APIs, graph UI, and MCP neighbor lookups, while canonical rows remain the source for rebuilding and cited context.

## Owner-Centered Nodes

The canonical graph starts at `person:self`, the owner profile. Page-authored content links the owner to projects and thoughts, and extracted entities and relationships extend the graph to people, code, sources, and decisions.

## Canonical Knowledge Graph

Canonical objects are stored as knowledge rows before they are projected into graph tables:

| Record | Key | Properties |
|---|---|---|
| `KnowledgeNode` | `id` | `kind`, `label`, `scope`, `confidence`, `extraction_method`, `citations`, `properties` |
| `KnowledgeRelationship` | `id` | `src_id`, `dst_id`, `rel_type`, `scope`, `confidence`, `extraction_method`, `citations`, `properties` |

`KnowledgeNode.kind` covers the owner profile, page-authored content, projects, thoughts, sources, extracted entities, people, code, and decisions as applicable. Relationships retain their citations and provenance metadata when projected into Kuzu.

## Legacy Compatibility Projection

The following `Page` and `Entity` tables and edges are the legacy compatibility projection used by existing graph APIs and wikilink behavior. They are derived from canonical knowledge and should not be read as the complete canonical object model.

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

Use the legacy rebuild command when content changes outside the normal write path or when ingest order left missing `REFERENCES` edges:

```bash
node packages/archivum-cli/src/index.js wiki rebuild-indexes
```

This command reinitializes the legacy page-based Qdrant and Kuzu projections from SQLite page content and metadata. It does not rebuild canonical knowledge projections, FTS, or the code lexical index.
