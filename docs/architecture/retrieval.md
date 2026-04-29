# Retrieval + Context Sizing

Archivum avoids sending “3 billion tokens” to Claude by strictly limiting what the LLM sees at query time.

## Query-time context: Qdrant first, then small excerpts

When you call `POST /api/query`, the backend:

1. Runs semantic retrieval using Qdrant over **chunk embeddings**:
   - Qdrant vectors are built from page content chunks (sliding window).
2. Pulls only the top-N hits (small number of chunks).
3. Deduplicates by page `slug` so you don’t get multiple chunks from the same page dominating the prompt.
4. Builds the LLM prompt from `excerpt` snippets from those hits.

Only those excerpts are included in the Claude synthesis prompt.

## Why ingest-time is still “expensive” but bounded

On ingest, Claude runs once per ingested source document (not per wiki-wide query), and the ingest agent truncates very long documents before asking for extraction.

## Where full content is used

The API may load full page content for “citations” metadata, but the **Claude synthesis prompt** uses only the retrieval excerpts built for the prompt.

