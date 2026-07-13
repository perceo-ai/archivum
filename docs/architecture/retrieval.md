# Retrieval and Context Sizing

Archivum answers questions by retrieving small snippets from Qdrant and only sending those snippets to the synthesis LLM.

## Query Flow

1. Embed the user question.
2. Search Qdrant for matching page chunks.
3. Deduplicate hits by page slug.
4. Fetch page titles from SQLite for citations.
5. Build a prompt from excerpts, not full wiki contents.
6. Ask the configured synthesis provider to answer using only the provided context.

Primary code:

| Concern | Path |
|---|---|
| REST query route | `apps/backend/archivum/api/query.py` |
| MCP query tool | `apps/backend/archivum/mcp/server.py` |
| Qdrant adapter | `apps/backend/archivum/db/qdrant_client.py` |
| Provider clients | `apps/backend/archivum/llm` |

## Why Context Stays Small

Query synthesis does not send the entire wiki to the model. It sends the top retrieved excerpts, capped and deduplicated by page. Full page content remains available for reading and citation metadata, but synthesis context is excerpt-based.

## Providers

Synthesis supports:

- Anthropic
- OpenRouter
- OpenAI-compatible providers
- Ollama through OpenAI-compatible calls

Embeddings support:

- local fastembed
- OpenAI-compatible embeddings
- OpenRouter
- Ollama
