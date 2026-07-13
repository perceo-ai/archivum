# Ingest Pipeline

Archivum ingests files and URLs into canonical markdown pages, then updates metadata, search, and graph indexes.

## Flow

1. Parse the source into clean text and metadata.
2. Send text to the configured extraction LLM.
3. Receive wiki pages, entities, and relationships as structured JSON.
4. Write markdown pages to the wiki directory.
5. Upsert page metadata and ingest logs in SQLite.
6. Chunk and embed content into Qdrant.
7. Upsert page/entity nodes and edges in Kuzu.

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

If a wikilink target is created later, run the rebuild endpoint/CLI to regenerate derived edges.
