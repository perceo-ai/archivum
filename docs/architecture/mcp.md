# MCP Server Tools

Archivum exposes the wiki through a built-in MCP server implemented in `apps/backend/archivum/mcp/server.py`.

## Transports

| Transport | Use |
|---|---|
| stdio | Desktop clients that run a local command, such as Claude Desktop |
| HTTP/SSE | Editors and web clients that connect to `http://localhost:8001/sse` |

Container default is SSE. Use `--stdio` when shelling into the MCP container from a desktop client.

## Client Examples

stdio:

```json
{
  "mcpServers": {
    "archivum": {
      "command": "docker",
      "args": ["exec", "-i", "archivum-mcp", "python", "-m", "archivum.mcp.server", "--stdio"],
      "env": { "MCP_API_KEY": "your-mcp-api-key" }
    }
  }
}
```

HTTP/SSE:

```json
{
  "mcpServers": {
    "archivum": {
      "url": "http://localhost:8001/sse",
      "headers": { "Authorization": "Bearer your-mcp-api-key" }
    }
  }
}
```

## Tools

| Tool | Purpose |
|---|---|
| `ingest_source(source, wiki_id)` | Process a file path or URL into the wiki |
| `search_wiki(query, top_k, wiki_id)` | Semantic search via Qdrant |
| `list_pages(wiki_id)` | List wiki pages from SQLite |
| `get_page(slug, wiki_id)` | Read full markdown for one page |
| `write_page(title, content, slug, tags, wiki_id)` | Queue a page create/update and wait for re-indexing |
| `life_daily_note(day, wiki_id)` | Create or return a daily note |
| `life_register_project(key, name, summary, status, wiki_id)` | Register a project and create its page |
| `life_create_task(title, project_key, page_slug, due_date, wiki_id)` | Create a Life OS task |
| `graph_neighbors(node_id, wiki_id)` | Return one-hop Kuzu neighbors |
| `export_graph_demo(output_dir)` | Write a self-contained demo graph export |
| `lint_wiki(wiki_id)` | Report broken wikilinks, orphan pages, and contradictory claims |
| `query(question, wiki_id)` | Retrieve context and synthesize an answer with citations |
| `dispatch_command(command, wiki_id)` | Text wrapper for ingest/search/query/pages/open/write/lint/graph actions |

Life OS tools are early product surfaces. Keep public positioning centered on the wiki, ingest, search, graph, sharing, export, and agent access.

## Security Note

`MCP_API_KEY` is configured for clients, but stdio clients run locally inside the trusted container context. Do not expose MCP SSE publicly without a trusted network, reverse proxy, or additional access controls.

## Validation

List MCP tools with Inspector:

```bash
cd apps/backend
UV_PYTHON=python3.12 npx @modelcontextprotocol/inspector --cli --method tools/list uv run python -m archivum.mcp.server --stdio
```
