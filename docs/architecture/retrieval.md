# Retrieval and Context Sizing

Markdown pages are the human editing surface. Canonical knowledge rows preserve the owner profile, page-authored content, projects, thoughts, extracted entities, relationships, citations, confidence, and extraction method. Qdrant, Kuzu, FTS, and code lexical indexes are rebuildable projections. Retrieval defaults to `person:self` when the caller does not provide another seed.

Archivum answers questions with bounded, cited context assembled from canonical knowledge and its retrieval projections. The synthesis LLM receives evidence-backed excerpts rather than an unbounded copy of the vault.

## Query Flow

1. Select `person:self` as the default seed when the caller does not provide another seed.
2. Search semantic, full-text, graph, and code lexical projections as appropriate for the request.
3. Resolve matches to canonical knowledge rows and their relationships.
4. Preserve citations, confidence, and extraction method on the returned context.
5. Build a bounded prompt from cited excerpts, not full wiki contents.
6. Ask the configured synthesis provider to answer using only the provided context.

Primary code:

| Concern | Path |
|---|---|
| REST query route | `apps/backend/archivum/api/query.py` |
| MCP query tool | `apps/backend/archivum/mcp/server.py` |
| Qdrant adapter | `apps/backend/archivum/db/qdrant_client.py` |
| Canonical context | `apps/backend/archivum/retrieval/context.py` |
| Hybrid retrieval | `apps/backend/archivum/retrieval/hybrid.py` |
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
