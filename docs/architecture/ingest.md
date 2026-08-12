# Ingest Pipeline

Archivum ingests files and URLs into editable canonical markdown pages, then projects their content and provenance into canonical knowledge rows and rebuildable search and graph indexes.

Markdown pages are the human editing surface. Canonical knowledge rows preserve the owner profile, page-authored content, projects, thoughts, extracted entities, relationships, citations, confidence, and extraction method. Qdrant, Kuzu, FTS, and code lexical indexes are rebuildable projections.

## Flow

1. Parse the source into clean text and metadata.
2. Send text to the configured extraction LLM.
3. Receive wiki pages, entities, and relationships as structured JSON.
4. Write editable markdown pages to the wiki directory.
5. Project page-authored content and extracted knowledge into canonical rows with citations, confidence, and extraction method.
6. Update operational metadata and FTS in SQLite.
7. Project semantic vectors into Qdrant, graph nodes and edges into Kuzu, and code entities into the rebuildable code lexical index.

Primary files:

| Concern | Path |
|---|---|
| Parser dispatch | `apps/backend/archivum/ingest/parsers.py` |
| Extraction prompt/client | `apps/backend/archivum/ingest/agent.py` |
| Pipeline orchestration | `apps/backend/archivum/ingest/pipeline.py` |
| REST ingest routes | `apps/backend/archivum/api/ingest.py` |
| Frontend ingest panel | `apps/frontend/src/components/IngestPanel.tsx` |

## Supported Sources

Backend parser support:

| Category | Formats |
|---|---|
| Text | `.md`, `.txt`, `.rst`, `.text` |
| Documents | `.pdf`, `.html`, `.htm`, `.epub` |
| Office | `.docx`, `.pptx`, `.xlsx`, `.xls` |
| Data | `.csv`, `.json`, `.jsonl` |
| Code/config | `.py`, `.js`, `.ts`, `.go`, `.rs`, `.sh`, `.bash`, `.zsh`, `.rb`, `.java`, `.c`, `.cpp`, `.h`, `.hpp`, `.kt`, `.swift`, `.php`, `.sql`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg` |
| Subtitles | `.srt`, `.vtt` |
| Email | `.eml`, `.mbox` |
| Images | `.png`, `.jpg`, `.jpeg`, `.webp`, `.gif` |
| Audio | `.mp3`, `.m4a`, `.wav`, `.ogg`, `.flac` |
| Video | `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm` |
| URLs | HTML, JSON, plain text, markdown, and text fallback |

The frontend file picker currently advertises a smaller subset. Backend support is broader than the UI hint.

## Optional Media Dependencies

- Image parsing uses Anthropic vision and requires `ANTHROPIC_API_KEY`.
- Audio parsing requires the `audio` optional dependency.
- Video parsing requires the `audio` optional dependency and system `ffmpeg`.
- Published Docker images omit Whisper, Torch, and ffmpeg.

## Graph Edges

Ingest creates these graph relationships:

| Edge | Source |
|---|---|
| `Page -[:REFERENCES]-> Page` | `[[wikilink]]` syntax when the target page exists |
| `Page -[:MENTIONS]-> Entity` | Case-insensitive entity-name match in page content |
| `Entity -[:RELATED_TO]-> Entity` | Extraction LLM `relationships[]` output |

If a wikilink target is created later, run the index refresh endpoint/CLI to add the legacy page-based `REFERENCES` edge projection. The current endpoint/CLI upserts page vectors, page nodes, and reference edges; it does not remove stale page projections or references, update entity/mention/relationship projections, or rebuild canonical knowledge projections, FTS, or the code lexical index.
