# Ingest Live Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Uploaded ingest tasks keep original filenames, expose live/recoverable status, and produce useful graph nodes even when LLM extraction falls back.

**Architecture:** Preserve the physical temp file path for parsing while passing an explicit display source through ingest logs, WebSocket events, and LLM document metadata. Use a single authenticated WebSocket as the live ingest channel: it sends a persisted-log snapshot on connect, streams pipeline events by wiki, and accepts typed control messages for future cancel/retry support. Improve fallback extraction with conservative proper-noun entities and relationships so graph output is not page-only when provider extraction fails.

**Tech Stack:** FastAPI, WebSocket, aiosqlite, React, TypeScript, Vite, Python unittest.

---

### Task 1: Preserve Uploaded Filenames Through Ingest

**Files:**
- Modify: `backend/archivum/api/ingest.py`
- Modify: `backend/archivum/ingest/pipeline.py`
- Test: `tests/test_ingest_pipeline.py`

- [x] **Step 1: Write the failing test**

```python
await ingest(
    Path(tmp.name),
    "default",
    lambda event: events.append(event) or asyncio.sleep(0),
    settings,
    source_name="resume.pdf",
)

create_log.assert_awaited_once_with("file", "resume.pdf", "default")
self.assertEqual(events[0]["file"], "resume.pdf")
self.assertEqual(parsed_doc_holder["doc"].metadata["filename"], "resume.pdf")
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv --project backend run python -m unittest tests.test_ingest_pipeline.IngestPipelineTests.test_ingest_uses_display_source_for_logs_events_and_extraction`

Expected: FAIL with `TypeError: ingest() got an unexpected keyword argument 'source_name'`

- [x] **Step 3: Implement filename preservation**

Add `source_name` to `ingest()` and `source_names` to `ingest_batch()`. Save uploads to a temp directory under a sanitized original basename and pass that basename into the pipeline.

- [x] **Step 4: Run test to verify it passes**

Run: `uv --project backend run python -m unittest tests.test_ingest_pipeline.IngestPipelineTests.test_ingest_uses_display_source_for_logs_events_and_extraction`

Expected: PASS

### Task 2: Stream Ingest Status Over WebSocket

**Files:**
- Create: `backend/archivum/ingest/events.py`
- Modify: `backend/archivum/api/ingest.py`
- Modify: `backend/archivum/ingest/pipeline.py`
- Modify: `backend/archivum/main.py`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/IngestPanel.tsx`
- Test: `tests/test_ingest_events.py`
- Test: `tests/test_ingest_websocket.py`

- [x] **Step 1: Write the failing test**

```python
async with subscribe("default") as queue:
    await publish("other", {"type": "start", "file": "other.pdf"})
    await publish("default", {"type": "start", "file": "resume.pdf"})

    event = await asyncio.wait_for(queue.get(), timeout=0.1)

self.assertEqual(event["file"], "resume.pdf")
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv --project backend run python -m unittest tests.test_ingest_events.IngestEventsTests.test_subscriber_receives_only_matching_wiki_events`

Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.ingest.events'`

- [x] **Step 3: Implement the event hub and WebSocket route**

Add a wiki-scoped in-memory event hub with bounded subscriber queues. Add `GET /api/ingest/ws` as a WebSocket route that authenticates from the access-token cookie or bearer header, sends a recent-log snapshot, forwards event-hub messages, and accepts typed control messages such as `{ "type": "control", "action": "ping" }`.

- [x] **Step 4: Move ingest progress to the socket**

Publish pipeline events to the event hub. Change file, URL, and batch ingest endpoints to return accepted-task JSON and run ingest work in background tasks. Open one WebSocket from `IngestPanel`, merge `snapshot` records into rows, and apply live `event` messages to the matching task.

- [x] **Step 5: Run tests and build**

Run: `uv --project backend run python -m unittest tests.test_ingest_events tests.test_ingest_websocket`

Expected: PASS

Run: `npm run build` from `frontend`

Expected: PASS

### Task 3: Avoid Page-Only Graphs On Fallback Extraction

**Files:**
- Modify: `backend/archivum/ingest/agent.py`
- Test: `tests/test_ingest_pipeline.py`

- [x] **Step 1: Write the failing test**

```python
result = agent._fallback_extraction(doc)

entity_names = {entity["name"] for entity in result.entities}
self.assertIn("Jane Doe", entity_names)
self.assertIn("Archivum", entity_names)
self.assertIn("Knowledge Graph Search", entity_names)
self.assertGreaterEqual(len(result.relationships), 2)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv --project backend run python -m unittest tests.test_ingest_pipeline.IngestPipelineTests.test_fallback_extraction_adds_entities_and_relationships_for_graph`

Expected: FAIL because `result.entities` is empty

- [x] **Step 3: Implement fallback entity extraction**

Add `_fallback_entities()` to extract basic proper-noun entities, classify obvious tech/org/person terms, and create `mentioned_with` relationships from the first entity to the next extracted entities.

- [x] **Step 4: Run verification**

Run: `uv --project backend run python -m unittest tests.test_ingest_pipeline tests.test_ingest_events tests.test_ingest_websocket`

Expected: PASS

Run: `npm run build` from `frontend`

Expected: PASS
