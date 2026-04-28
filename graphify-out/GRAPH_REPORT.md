# Graph Report - .  (2026-04-28)

## Corpus Check
- Corpus is ~5,428 words - fits in a single context window. You may not need a graph.

## Summary
- 32 nodes · 44 edges · 5 communities detected
- Extraction: 93% EXTRACTED · 7% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Ingest & Storage Pipeline|Ingest & Storage Pipeline]]
- [[_COMMUNITY_Core Platform & Vision|Core Platform & Vision]]
- [[_COMMUNITY_AI Query & MCP Layer|AI Query & MCP Layer]]
- [[_COMMUNITY_Remote Access & Security|Remote Access & Security]]
- [[_COMMUNITY_Web Editor & Graph UI|Web Editor & Graph UI]]

## God Nodes (most connected - your core abstractions)
1. `Archivum` - 12 edges
2. `Ingest Pipeline` - 10 edges
3. `MCP Server` - 7 edges
4. `Neo4j` - 6 edges
5. `Qdrant` - 5 edges
6. `Query Engine` - 5 edges
7. `Web UI` - 3 edges
8. `CodeMirror 6 Editor` - 3 edges
9. `Markdown as Canonical Format` - 3 edges
10. `Graph View` - 3 edges

## Surprising Connections (you probably didn't know these)
- `CodeMirror 6 Editor` --semantically_similar_to--> `Obsidian`  [INFERRED] [semantically similar]
  archivum-prd-v1.0.md → archivum-prd-v1.0.md  _Bridges community 4 → community 1_
- `Query Engine` --semantically_similar_to--> `NotebookLM`  [INFERRED] [semantically similar]
  archivum-prd-v1.0.md → archivum-prd-v1.0.md  _Bridges community 2 → community 1_
- `Archivum` --references--> `Ingest Pipeline`  [EXTRACTED]
  archivum-prd-v1.0.md → archivum-prd-v1.0.md  _Bridges community 1 → community 0_
- `Ingest Pipeline` --references--> `Qdrant`  [EXTRACTED]
  archivum-prd-v1.0.md → archivum-prd-v1.0.md  _Bridges community 0 → community 2_
- `MCP Server` --references--> `Graph View`  [EXTRACTED]
  archivum-prd-v1.0.md → archivum-prd-v1.0.md  _Bridges community 2 → community 4_

## Hyperedges (group relationships)
- **Ingest to Knowledge Graph Flow** — archivum_prd_v1_0_ingest_pipeline, archivum_prd_v1_0_wiki_agent, archivum_prd_v1_0_markdown_canonical, archivum_prd_v1_0_qdrant, archivum_prd_v1_0_neo4j [EXTRACTED 1.00]
- **Query Synthesis Pipeline** — archivum_prd_v1_0_query_engine, archivum_prd_v1_0_semantic_search, archivum_prd_v1_0_qdrant, archivum_prd_v1_0_neo4j [EXTRACTED 1.00]
- **Remote Access Security Stack** — archivum_prd_v1_0_tailscale, archivum_prd_v1_0_cloudflare_tunnel, archivum_prd_v1_0_caddy [EXTRACTED 1.00]

## Communities

### Community 0 - "Ingest & Storage Pipeline"
Cohesion: 0.25
Nodes (9): BeautifulSoup, Ingest Pipeline, Kuzu, Markdown as Canonical Format, Neo4j, Playwright, PyMuPDF, Whisper (+1 more)

### Community 1 - "Core Platform & Vision"
Cohesion: 0.25
Nodes (8): Archivum, Docker Compose Stack, Memex (Vannevar Bush), Multi-tenancy (Future), NotebookLM, Obsidian, Ollama, REST API

### Community 2 - "AI Query & MCP Layer"
Cohesion: 0.47
Nodes (6): Wiki Lint / Health Check, MCP (Model Context Protocol), MCP Server, Qdrant, Query Engine, Semantic Search

### Community 3 - "Remote Access & Security"
Cohesion: 0.4
Nodes (5): Caddy Reverse Proxy, Cloudflare Tunnel, Security Architecture, Share Links, Tailscale

### Community 4 - "Web Editor & Graph UI"
Cohesion: 0.5
Nodes (4): CodeMirror 6 Editor, Graph View, Web UI, Wikilinks ([[page name]])

## Knowledge Gaps
- **15 isolated node(s):** `REST API`, `Kuzu`, `Share Links`, `Wikilinks ([[page name]])`, `Tailscale` (+10 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Archivum` connect `Core Platform & Vision` to `Ingest & Storage Pipeline`, `AI Query & MCP Layer`, `Web Editor & Graph UI`?**
  _High betweenness centrality (0.407) - this node is a cross-community bridge._
- **Why does `Ingest Pipeline` connect `Ingest & Storage Pipeline` to `Core Platform & Vision`, `AI Query & MCP Layer`?**
  _High betweenness centrality (0.234) - this node is a cross-community bridge._
- **Why does `MCP Server` connect `AI Query & MCP Layer` to `Ingest & Storage Pipeline`, `Core Platform & Vision`, `Web Editor & Graph UI`?**
  _High betweenness centrality (0.149) - this node is a cross-community bridge._
- **What connects `REST API`, `Kuzu`, `Share Links` to the rest of the system?**
  _15 weakly-connected nodes found - possible documentation gaps or missing edges._