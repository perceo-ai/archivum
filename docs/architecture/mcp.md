# MCP Server Tools

Archivum exposes functionality via an MCP server (stdio + SSE transports).

The MCP server is implemented in `backend/archivum/mcp/server.py`.

## Tools (high level)

- `ingest_source(source, wiki_id)`
  - Runs the full ingest pipeline for a file path or URL.

- `search_wiki(query, top_k, wiki_id)`
  - Semantic search via Qdrant; returns ranked items with excerpts.

- `list_pages(wiki_id)`
  - Lists pages stored in SQLite for the given `wiki_id`.

- `get_page(slug, wiki_id)`
  - Returns full markdown content by slug.

- `write_page(title, content, ...)`
  - Creates or updates a page and re-indexes it (Qdrant + Kuzu).

- `query(question, wiki_id)`
  - Runs question answering by retrieving relevant snippets and synthesizing an answer with citations.

- `graph_neighbors(node_id, wiki_id)`
  - Returns 1-hop Kuzu neighbors for graph navigation.

- `lint_wiki(wiki_id)`
  - Reports broken wikilinks and orphan pages.

