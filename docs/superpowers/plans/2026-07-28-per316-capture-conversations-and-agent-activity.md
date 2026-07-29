# PER-316: Capture AI Conversations & Agent Activity — Implementation Plan

**For agentic workers.** Execute tasks in order. Each task is TDD: write the failing
test, run it (confirm FAIL), write the minimal implementation, run it (confirm PASS),
then commit with the exact command given. Steps are sized for 2–5 minutes. All types are
defined in this document — no placeholders.

## Goal

Build the AI-native capture layer that records user-visible AI conversations, tool
activity, changed artifacts, decisions, and task outcomes **as Sources in the immutable
store** (L0) and their lineage in L1 (`Document` → `Chunk`), plus `Event` / `Claim`
knowledge objects with provenance back to the originating agent session. Two capture
paths:

1. **Native capture** — a writer used by Perceo-controlled agent workers (this Claude
   Code / agent-worker environment) that records turns and tool calls live.
2. **Imports** — a connector interface plus concrete importers for third-party AI clients
   (Claude Code transcript JSONL first; a generic ChatGPT export importer second).

Both paths converge on one canonical conversation schema, are content-addressed and
idempotent (re-import is a no-op), preserve provenance, and **never store hidden model
reasoning** — only user-visible turns and tool calls.

## Architecture

This epic sits at **L0 → L1** (per architecture spec §2, §4, §5). Capture normalizes any
AI session into a canonical `Conversation` value object, then:

- Serializes it to a stable canonical JSON blob and writes it via PER-315's `SourceStore`
  (content-addressed, versioned → L0).
- Registers a `Source` (`source_type="conversation"`), a `Document` (normalized
  transcript), and one `Chunk` per turn (evidence anchors → L1).
- Emits `Event` rows (session-started, tool-call, decision, outcome) and `Claim` rows
  (decisions as contestable facts), each carrying `provenance` (chunk_id + span),
  `confidence`, and `extraction_method` per spec §4 invariant.
- Links the agent session to its Source via a `provenance` edge so downstream graph
  construction (PER-317) can connect a decision to the conversation that made it.

Redaction runs **before** content-addressing so hidden reasoning never touches L0.

## Tech Stack

- Python 3.12, async, `aiosqlite` (matches `archivum/db/sqlite.py`).
- `pytest` + `pytest-asyncio` (asyncio_mode configured in Task 0).
- `hashlib.sha256` for content addressing (consistent with PER-315 / spec §2 L0).
- Stdlib `json`, `dataclasses`, `datetime` (UTC). No new third-party dependencies.
- FastAPI/MCP wiring reuses existing `archivum/mcp/server.py` patterns.

## Global Constraints

Copied from the architecture spec (§1 non-goals, §4 invariant, §6 trust invariants) —
these bind every task:

- **No hidden reasoning.** Only user-visible conversation turns and tool activity are
  ever captured or stored. Model chain-of-thought / `thinking` / `reasoning` blocks are
  stripped by the redactor *before* content-addressing and never reach L0, L1, or any
  index. (spec §1, §5.)
- **Provenance invariant.** Every L1 knowledge object (`Event`, `Claim`) carries ≥1
  provenance link (`chunk_id` + span), a `confidence` score, and an
  `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`. An object with no evidence
  cannot exist. (spec §4, §6.2, §6.3.)
- **Evidence is immutable.** Generated knowledge never mutates L0. Re-capturing a changed
  session creates a new `Source` version, never overwrites. (spec §6.1, §2 L0.)
- **Evolve in place.** Extend the existing SQLite schema and reuse existing modules
  (`db/sqlite.py`, `ingest/`, `mcp/`); do not rewrite. New tables are additive. (spec §3,
  §9.)
- **Content-addressed & idempotent.** Identical session content produces the identical
  `content_hash`; re-import is a no-op (spec §2, §5 semantic cache).
- **Rebuildable indexes.** Nothing here writes a source of truth into L2; conversation
  chunks feed L2 the same way document chunks do. (spec §6.6.)

## File Structure

```
apps/backend/
  pyproject.toml                              # add [tool.pytest.ini_options] (Task 0)
  tests/
    conftest.py                               # temp-dir Settings + init_db fixtures (Task 0)
    capture/
      __init__.py
      test_schema.py                          # Task 1
      test_redaction.py                        # Task 2
      test_canonical_json.py                   # Task 3
      test_capture_store.py                    # Tasks 5,6
      test_native_writer.py                    # Task 7
      test_importer_base.py                    # Task 8
      test_claude_code_importer.py             # Tasks 9,10
      test_chatgpt_importer.py                 # Task 11
      test_provenance_events.py               # Task 12
      test_idempotency.py                      # Task 13
      test_no_hidden_reasoning.py             # Task 14
      test_mcp_capture.py                      # Task 15
    fixtures/
      claude_code_session.jsonl               # Task 9 (real sample transcript)
      chatgpt_export.json                     # Task 11 (real sample export)
  archivum/
    capture/
      __init__.py                             # public exports
      schema.py                               # Conversation/Turn/ToolCall/Decision/Outcome (Task 1)
      redaction.py                            # strip hidden reasoning (Task 2)
      canonical.py                            # deterministic canonical JSON + hashing (Task 3)
      store.py                                # CaptureStore: Conversation → L0+L1 (Tasks 5,6)
      provenance.py                           # Event/Claim emission + session→Source link (Task 12)
      native.py                               # NativeCaptureWriter for agent workers (Task 7)
      importers/
        __init__.py                           # registry (Task 8)
        base.py                               # ImportConnector protocol + ImportResult (Task 8)
        claude_code.py                        # JSONL transcript importer (Tasks 9,10)
        chatgpt.py                            # ChatGPT export importer (Task 11)
    db/
      capture_sql.py                          # conversation-capture DDL + CRUD (Task 4)
    mcp/
      server.py                               # add capture_conversation tool (Task 15, edit)
```

## Upstream Dependencies

**PER-315 (Immutable Source Store & Ingestion) — its plan does not yet exist at authoring
time.** Per instructions we consume the spec's L0/L1 model directly and assume the
following PER-315 surface. If PER-315's actual plan differs, adapt the thin adapter in
Task 5 only.

Assumed PER-315 interfaces (spec §2, §4):

- **`SourceStore`** (`archivum/ingest/source_store.py`), async, content-addressed L0 blob
  store:
  - `async def put(self, data: bytes, *, source_type: str, origin_uri: str, scope: str) -> StoredSource`
  - `StoredSource` dataclass: `source_id: int`, `content_hash: str` (sha256 hex),
    `version: int`, `created: bool` (False when the hash already existed → dedup hit).
  - `put` is idempotent on `content_hash`: identical bytes return the existing
    `StoredSource` with `created=False` and do not write a new version.
- **`ingest_source(store, data, *, source_type, origin_uri, scope) -> IngestResult`**
  entrypoint that registers `Source` and (for text) a `Document` — **for conversations we
  do NOT use it**; Task 5 registers `Document`/`Chunk` explicitly because a conversation's
  Document layout (one chunk per turn) is capture-specific.
- **L1 tables** `sources`, `documents`, `chunks` exist with the spec §4 fields. If PER-315
  has not yet created them, Task 4 creates them idempotently with `CREATE TABLE IF NOT
  EXISTS` using the spec §4 field set (no conflict: identical definitions).

**Assumption note:** If PER-315 already provides `documents`/`chunks` CRUD, Task 4's CRUD
becomes thin wrappers; the DDL is `IF NOT EXISTS` so it is safe either way. `SourceStore`
is wrapped behind `CaptureStore` (Task 5) so a signature change is a one-file fix.

---

### Task 0 — Test harness & fixtures

**Files:** `apps/backend/pyproject.toml`, `apps/backend/tests/conftest.py`,
`apps/backend/tests/capture/__init__.py`

**Interfaces:**
- Produces pytest fixtures `settings` (`Settings` with all data paths under a `tmp_path`)
  and `initialized_db` (calls `archivum.db.sqlite.init_db(settings)` +
  `archivum.db.capture_sql.init_capture_schema(settings)`).

Steps:

- [ ] Add pytest config to `pyproject.toml`:
```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```
- [ ] Create `apps/backend/tests/capture/__init__.py` (empty file).
- [ ] Write `apps/backend/tests/conftest.py`:
```python
from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio

from archivum.config import Settings
from archivum.db import sqlite


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        db_path=tmp_path / "archivum.db",
        kuzu_path=tmp_path / "kuzu",
    )


@pytest_asyncio.fixture
async def initialized_db(settings: Settings) -> Settings:
    from archivum.db import capture_sql

    await sqlite.init_db(settings)
    await capture_sql.init_capture_schema(settings)
    return settings
```
- [ ] Run: `cd apps/backend && uv run pytest tests/ -q` — expect **collection error**
  (`archivum.db.capture_sql` missing). This confirms the harness loads.
- [ ] Commit: `git add apps/backend/pyproject.toml apps/backend/tests && git commit -m "test(capture): add pytest harness and db fixtures for PER-316"`

---

### Task 1 — Canonical conversation schema

**Files:** `apps/backend/archivum/capture/__init__.py`,
`apps/backend/archivum/capture/schema.py`,
`apps/backend/tests/capture/test_schema.py`

**Interfaces (Produces):** frozen dataclasses that model any AI session.
```python
# archivum/capture/schema.py
Role = Literal["user", "assistant", "tool", "system"]
ExtractionMethod = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]

@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str                      # tool/function name
    arguments: dict[str, Any]      # user-visible call args (already redacted)
    result: str | None             # user-visible result text, may be None if pending
    call_id: str | None = None     # provider call id, for correlation
    started_at: str | None = None  # ISO-8601 UTC
    ok: bool = True                # False if the tool errored

@dataclass(frozen=True, slots=True)
class Turn:
    role: Role
    text: str                      # user-visible content only (no reasoning)
    ts: str                        # ISO-8601 UTC timestamp
    tool_calls: tuple[ToolCall, ...] = ()

@dataclass(frozen=True, slots=True)
class Decision:
    statement: str                 # e.g. "Use SQLite as canonical store"
    rationale: str = ""
    turn_index: int = -1           # index into Conversation.turns for provenance

@dataclass(frozen=True, slots=True)
class Outcome:
    task: str                      # what was attempted
    status: Literal["success", "failure", "partial", "unknown"]
    detail: str = ""
    turn_index: int = -1

@dataclass(frozen=True, slots=True)
class Conversation:
    session_id: str                # stable id from the source interface
    interface: str                 # "claude_code_native" | "claude_code_import" | "chatgpt" ...
    started_at: str                # ISO-8601 UTC
    turns: tuple[Turn, ...]
    decisions: tuple[Decision, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    scope: str = "personal"        # spec §4 scope label
    origin_uri: str = ""           # provenance: file path / url / worker id
    metadata: dict[str, Any] = field(default_factory=dict)
```

Steps:

- [ ] Write `tests/capture/test_schema.py`:
```python
from archivum.capture.schema import Conversation, Turn, ToolCall


def test_conversation_is_immutable_and_nests_tool_calls():
    tc = ToolCall(name="Read", arguments={"path": "/x"}, result="ok")
    turn = Turn(role="assistant", text="reading file", ts="2026-07-28T00:00:00Z",
                tool_calls=(tc,))
    conv = Conversation(session_id="s1", interface="claude_code_native",
                        started_at="2026-07-28T00:00:00Z", turns=(turn,))
    assert conv.turns[0].tool_calls[0].name == "Read"
    assert conv.turns[0].tool_calls[0].ok is True
    import dataclasses
    try:
        conv.session_id = "s2"  # type: ignore[misc]
        assert False, "should be frozen"
    except dataclasses.FrozenInstanceError:
        pass
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_schema.py -q` — expect **FAIL** (module missing).
- [ ] Implement `archivum/capture/schema.py` with the dataclasses above (add
  `from __future__ import annotations`, imports: `dataclasses.dataclass/field`,
  `typing.Any/Literal`).
- [ ] Write `archivum/capture/__init__.py`:
```python
from archivum.capture.schema import (
    Conversation, Turn, ToolCall, Decision, Outcome,
)

__all__ = ["Conversation", "Turn", "ToolCall", "Decision", "Outcome"]
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_schema.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture apps/backend/tests/capture/test_schema.py && git commit -m "feat(capture): canonical conversation schema"`

---

### Task 2 — Redaction (strip hidden reasoning)

**Files:** `apps/backend/archivum/capture/redaction.py`,
`apps/backend/tests/capture/test_redaction.py`

**Interfaces:**
- Consumes: raw provider message dicts (varied shapes).
- Produces:
```python
HIDDEN_BLOCK_TYPES: frozenset[str]  # {"thinking", "reasoning", "redacted_thinking"}

def visible_text_from_blocks(content: Any) -> str:
    """Given a str or a list of provider content blocks, return only user-visible text.
    Drops any block whose type is in HIDDEN_BLOCK_TYPES. Keeps text/tool_use/tool_result."""

def redact_turn_text(text: str) -> str:
    """Strip inline <thinking>...</thinking> / <reasoning>...</reasoning> spans."""
```

Steps:

- [ ] Write `tests/capture/test_redaction.py`:
```python
from archivum.capture.redaction import visible_text_from_blocks, redact_turn_text


def test_drops_thinking_blocks_keeps_text():
    blocks = [
        {"type": "thinking", "thinking": "secret chain of thought"},
        {"type": "text", "text": "here is the answer"},
    ]
    out = visible_text_from_blocks(blocks)
    assert "secret" not in out
    assert "here is the answer" in out


def test_redacts_inline_reasoning_tags():
    assert "secret" not in redact_turn_text("a <thinking>secret</thinking> b")
    assert "reason" not in redact_turn_text("x <reasoning>reason</reasoning> y")


def test_plain_string_passthrough():
    assert visible_text_from_blocks("hello") == "hello"
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_redaction.py -q` — expect **FAIL**.
- [ ] Implement `archivum/capture/redaction.py`:
```python
from __future__ import annotations

import re
from typing import Any

HIDDEN_BLOCK_TYPES: frozenset[str] = frozenset(
    {"thinking", "reasoning", "redacted_thinking"}
)
_INLINE = re.compile(r"<(thinking|reasoning)>.*?</\1>", re.DOTALL | re.IGNORECASE)


def redact_turn_text(text: str) -> str:
    return _INLINE.sub("", text or "").strip()


def visible_text_from_blocks(content: Any) -> str:
    if isinstance(content, str):
        return redact_turn_text(content)
    parts: list[str] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        btype = block.get("type", "")
        if btype in HIDDEN_BLOCK_TYPES:
            continue
        if btype == "text":
            parts.append(str(block.get("text", "")))
        elif btype == "tool_result":
            parts.append(str(block.get("content", "")))
    return redact_turn_text("\n".join(p for p in parts if p))
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_redaction.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/redaction.py apps/backend/tests/capture/test_redaction.py && git commit -m "feat(capture): redaction strips hidden model reasoning"`

---

### Task 3 — Canonical JSON & content hashing

**Files:** `apps/backend/archivum/capture/canonical.py`,
`apps/backend/tests/capture/test_canonical_json.py`

**Interfaces:**
- Consumes: `Conversation`.
- Produces:
```python
def to_canonical_dict(conv: Conversation) -> dict[str, Any]  # stable, sorted
def to_canonical_bytes(conv: Conversation) -> bytes          # utf-8 JSON, sorted keys
def content_hash(conv: Conversation) -> str                  # sha256 hex of bytes
```
Determinism rule: identical conversation content → identical bytes → identical hash
(dedup key for PER-315). `metadata` is excluded from the hash (transport-only) so
re-imports with differing incidental metadata still dedup.

Steps:

- [ ] Write `tests/capture/test_canonical_json.py`:
```python
from archivum.capture.schema import Conversation, Turn
from archivum.capture.canonical import content_hash, to_canonical_bytes


def _conv(meta):
    return Conversation(session_id="s1", interface="x", started_at="2026-07-28T00:00:00Z",
                        turns=(Turn(role="user", text="hi", ts="2026-07-28T00:00:00Z"),),
                        metadata=meta)


def test_hash_stable_and_ignores_metadata():
    a = content_hash(_conv({"a": 1}))
    b = content_hash(_conv({"b": 2}))
    assert a == b and len(a) == 64


def test_bytes_are_sorted_json():
    raw = to_canonical_bytes(_conv({}))
    assert raw.startswith(b"{") and b'"interface"' in raw
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_canonical_json.py -q` — expect **FAIL**.
- [ ] Implement `archivum/capture/canonical.py`:
```python
from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

from archivum.capture.schema import Conversation


def to_canonical_dict(conv: Conversation) -> dict[str, Any]:
    d = dataclasses.asdict(conv)
    d.pop("metadata", None)  # transport-only, excluded from identity
    return d


def to_canonical_bytes(conv: Conversation) -> bytes:
    return json.dumps(
        to_canonical_dict(conv), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_hash(conv: Conversation) -> str:
    return hashlib.sha256(to_canonical_bytes(conv)).hexdigest()
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_canonical_json.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/canonical.py apps/backend/tests/capture/test_canonical_json.py && git commit -m "feat(capture): deterministic canonical json + content hash"`

---

### Task 4 — Capture DB schema & CRUD (documents, chunks, events, claims)

**Files:** `apps/backend/archivum/db/capture_sql.py`,
`apps/backend/tests/capture/test_capture_store.py` (schema portion)

**Interfaces (Produces):**
```python
async def init_capture_schema(settings: Settings) -> None
async def insert_document(source_id: int, mime: str, normalized_hash: str, text: str) -> int
async def insert_chunk(document_id: int, seq: int, span_start: int, span_end: int,
                       text_hash: str) -> int
async def insert_event(kind: str, chunk_id: int, occurred_at: str, summary: str,
                       extraction_method: str, confidence: float,
                       metadata: dict) -> int
async def insert_claim(statement: str, chunk_id: int, extraction_method: str,
                       confidence: float, valid_from: str, recorded_at: str,
                       metadata: dict) -> int
async def get_document_by_source(source_id: int) -> dict | None
async def list_events_for_source(source_id: int) -> list[dict]
```
DDL (additive, `IF NOT EXISTS`; `sources` assumed from PER-315, else created here):
```sql
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    source_type TEXT NOT NULL, origin_uri TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'personal',
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(content_hash, version)
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    mime TEXT NOT NULL, normalized_hash TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL, span_start INTEGER NOT NULL, span_end INTEGER NOT NULL,
    text_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL, chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    occurred_at TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '',
    extraction_method TEXT NOT NULL, confidence REAL NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    statement TEXT NOT NULL,
    chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    extraction_method TEXT NOT NULL, confidence REAL NOT NULL,
    valid_from TEXT, recorded_at TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_events_chunk ON events(chunk_id);
```

Steps:

- [ ] Write the schema test in `tests/capture/test_capture_store.py`:
```python
import pytest

from archivum.db import capture_sql
from archivum.db.sqlite import get_db


@pytest.mark.asyncio
async def test_schema_creates_capture_tables(initialized_db):
    async with get_db() as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name IN ('sources','documents','chunks','events','claims')"
        ) as cur:
            names = {r["name"] for r in await cur.fetchall()}
    assert names == {"sources", "documents", "chunks", "events", "claims"}


@pytest.mark.asyncio
async def test_insert_document_and_chunk(initialized_db):
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO sources (content_hash, source_type) VALUES ('h1','conversation')"
        )
        await db.commit()
        source_id = cur.lastrowid
    doc_id = await capture_sql.insert_document(source_id, "application/json", "n1", "text")
    chunk_id = await capture_sql.insert_chunk(doc_id, 0, 0, 4, "th")
    assert doc_id > 0 and chunk_id > 0
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_capture_store.py -q` — expect **FAIL**.
- [ ] Implement `archivum/db/capture_sql.py`: module-level `_CAPTURE_SCHEMA` string with the
  DDL above; `init_capture_schema` runs `await db.executescript(_CAPTURE_SCHEMA)` inside
  `get_db()` and commits (mirror `sqlite.init_db`). Implement the CRUD functions using
  `async with get_db() as db:` and `json.dumps` for `metadata` (mirror existing
  `sqlite.py` style).
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_capture_store.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/db/capture_sql.py apps/backend/tests/capture/test_capture_store.py && git commit -m "feat(capture): additive L1 schema for documents/chunks/events/claims"`

---

### Task 5 — CaptureStore: Conversation → L0 Source + L1 Document/Chunks

**Files:** `apps/backend/archivum/capture/store.py`,
`apps/backend/tests/capture/test_capture_store.py` (store portion)

**Interfaces:**
- Consumes: `Conversation`; PER-315 `SourceStore.put` (wrapped, see Upstream Deps).
- Produces:
```python
@dataclass(frozen=True)
class CaptureResult:
    source_id: int
    content_hash: str
    document_id: int
    chunk_ids: tuple[int, ...]   # one per turn, in order
    created: bool                # False => dedup no-op (source already existed)

class CaptureStore:
    def __init__(self, source_store: "SourceStore") -> None: ...
    async def capture(self, conv: Conversation) -> CaptureResult: ...
```
Behavior: redact-then-canonicalize (Task 2/3 already produce visible-only text; store
asserts no hidden types survive), compute `content_hash`, call `source_store.put(bytes,
source_type="conversation", origin_uri=conv.origin_uri, scope=conv.scope)`. If
`stored.created is False`, return the existing document/chunks (idempotent). Else insert a
`Document` (mime `application/json`, `normalized_hash = content_hash`, text = the
human-readable transcript) and one `Chunk` per turn whose `span_start/span_end` index into
that transcript text.

For test isolation, provide an in-file `_SqliteSourceStore` adapter that implements the
assumed `SourceStore.put` against the `sources` table, used **only** if PER-315's real
store is unavailable at construction time. Production wires the real store.

Steps:

- [ ] Append to `tests/capture/test_capture_store.py`:
```python
from archivum.capture.schema import Conversation, Turn
from archivum.capture.store import CaptureStore, _SqliteSourceStore


def _conv():
    return Conversation(
        session_id="s1", interface="claude_code_native",
        started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="do X", ts="2026-07-28T00:00:00Z"),
               Turn(role="assistant", text="did X", ts="2026-07-28T00:00:01Z")),
    )


@pytest.mark.asyncio
async def test_capture_writes_source_document_and_chunk_per_turn(initialized_db):
    store = CaptureStore(_SqliteSourceStore())
    res = await store.capture(_conv())
    assert res.created is True
    assert len(res.chunk_ids) == 2
    doc = await capture_sql.get_document_by_source(res.source_id)
    assert "did X" in doc["text"]
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_capture_store.py -q` — expect **FAIL**.
- [ ] Implement `_SqliteSourceStore` (put: upsert on `content_hash`, return `StoredSource`
  with `created`), `CaptureStore.capture`. Build transcript text as
  `"\n\n".join(f"[{t.role}] {t.text}" + tool lines)`, tracking each turn's char span for
  chunks. Insert document + chunks via `capture_sql`.
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_capture_store.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/store.py apps/backend/tests/capture/test_capture_store.py && git commit -m "feat(capture): CaptureStore writes conversation to L0 source + L1 doc/chunks"`

---

### Task 6 — Dedup vs PER-315 content-addressing (idempotent capture)

**Files:** `apps/backend/archivum/capture/store.py` (verify),
`apps/backend/tests/capture/test_capture_store.py` (dedup portion)

**Interfaces:** no new API; asserts `CaptureStore.capture` is idempotent on identical
content and returns `created=False` without inserting duplicate documents/chunks.

Steps:

- [ ] Append to `tests/capture/test_capture_store.py`:
```python
@pytest.mark.asyncio
async def test_capture_is_idempotent_on_identical_content(initialized_db):
    store = CaptureStore(_SqliteSourceStore())
    r1 = await store.capture(_conv())
    r2 = await store.capture(_conv())
    assert r1.content_hash == r2.content_hash
    assert r2.created is False
    assert r1.document_id == r2.document_id
    async with get_db() as db:
        async with db.execute("SELECT COUNT(*) AS n FROM chunks") as cur:
            n = (await cur.fetchone())["n"]
    assert n == 2  # not duplicated
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_capture_store.py::test_capture_is_idempotent_on_identical_content -q` — expect **FAIL** if the store re-inserts.
- [ ] Fix `CaptureStore.capture`: when `stored.created is False`, look up the existing
  document via `capture_sql.get_document_by_source(stored.source_id)` and its chunk ids;
  return `CaptureResult(created=False, ...)` without inserting.
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_capture_store.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/store.py apps/backend/tests/capture/test_capture_store.py && git commit -m "feat(capture): dedup capture against content-addressed source store"`

---

### Task 7 — Native capture writer for agent workers

**Files:** `apps/backend/archivum/capture/native.py`,
`apps/backend/tests/capture/test_native_writer.py`

**Interfaces:**
- Consumes: live turn/tool events from a Perceo agent worker; `CaptureStore`.
- Produces:
```python
class NativeCaptureWriter:
    def __init__(self, store: CaptureStore, *, session_id: str,
                 interface: str = "claude_code_native", scope: str = "personal",
                 origin_uri: str = "") -> None: ...
    def record_turn(self, role: Role, text: str,
                    tool_calls: Sequence[ToolCall] = ()) -> None: ...
    def record_tool_call(self, name: str, arguments: dict, result: str | None,
                         ok: bool = True) -> None: ...   # attaches to last assistant turn
    def record_decision(self, statement: str, rationale: str = "") -> None: ...
    def record_outcome(self, task: str, status: str, detail: str = "") -> None: ...
    def build(self) -> Conversation: ...
    async def flush(self) -> CaptureResult: ...   # build() -> store.capture()
```
`record_turn`/`record_tool_call` run text through `redact_turn_text` on the way in so
hidden reasoning never enters the buffer. Timestamps default to `datetime.now(UTC)`.

Steps:

- [ ] Write `tests/capture/test_native_writer.py`:
```python
import pytest

from archivum.capture.native import NativeCaptureWriter
from archivum.capture.store import CaptureStore, _SqliteSourceStore


@pytest.mark.asyncio
async def test_native_writer_records_and_flushes(initialized_db):
    w = NativeCaptureWriter(CaptureStore(_SqliteSourceStore()), session_id="s1")
    w.record_turn("user", "add a feature")
    w.record_turn("assistant", "<thinking>hidden</thinking> on it")
    w.record_tool_call("Edit", {"path": "/a.py"}, "written")
    w.record_decision("use dataclasses", "simpler")
    conv = w.build()
    assert "hidden" not in conv.turns[1].text
    assert conv.turns[1].tool_calls[0].name == "Edit"
    assert conv.decisions[0].statement == "use dataclasses"
    res = await w.flush()
    assert res.created is True and len(res.chunk_ids) == 2
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_native_writer.py -q` — expect **FAIL**.
- [ ] Implement `NativeCaptureWriter`: buffer `list[Turn]`, `list[Decision]`,
  `list[Outcome]`. `record_tool_call` appends a `ToolCall` (args passed through, result via
  `redact_turn_text`) to the most recent assistant turn (rebuild that frozen `Turn` with
  the appended tool_calls tuple). `build` returns a `Conversation`; `flush` calls
  `store.capture`.
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_native_writer.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/native.py apps/backend/tests/capture/test_native_writer.py && git commit -m "feat(capture): native capture writer for agent workers"`

---

### Task 8 — Import connector interface + registry

**Files:** `apps/backend/archivum/capture/importers/__init__.py`,
`apps/backend/archivum/capture/importers/base.py`,
`apps/backend/tests/capture/test_importer_base.py`

**Interfaces:**
```python
# base.py
@dataclass(frozen=True)
class ImportResult:
    conversations: tuple[Conversation, ...]
    interface: str

class ImportConnector(Protocol):
    interface: str
    def can_handle(self, path: Path) -> bool: ...
    def parse(self, path: Path) -> ImportResult: ...  # pure: file -> Conversations

# __init__.py
def register(connector: ImportConnector) -> None: ...
def connector_for(path: Path) -> ImportConnector | None: ...
def all_connectors() -> tuple[ImportConnector, ...]: ...
```
Connectors are pure parsers (no DB); the caller feeds each `Conversation` to
`CaptureStore.capture`, so idempotency/dedup (Tasks 5–6) apply uniformly to imports.

Steps:

- [ ] Write `tests/capture/test_importer_base.py`:
```python
from pathlib import Path

from archivum.capture.importers import register, connector_for, all_connectors
from archivum.capture.importers.base import ImportResult


class _Fake:
    interface = "fake"
    def can_handle(self, path): return path.suffix == ".fake"
    def parse(self, path): return ImportResult(conversations=(), interface="fake")


def test_registry_dispatches_by_can_handle():
    register(_Fake())
    assert connector_for(Path("x.fake")).interface == "fake"
    assert connector_for(Path("x.nope")) is None
    assert any(c.interface == "fake" for c in all_connectors())
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_importer_base.py -q` — expect **FAIL**.
- [ ] Implement `base.py` (dataclass + Protocol) and `__init__.py` (module-level
  `_REGISTRY: list[ImportConnector]`, `register`, `connector_for` returns first whose
  `can_handle` is True, `all_connectors`).
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_importer_base.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/importers/__init__.py apps/backend/archivum/capture/importers/base.py apps/backend/tests/capture/test_importer_base.py && git commit -m "feat(capture): import connector protocol + registry"`

---

### Task 9 — Claude Code transcript importer (JSONL parse)

**Files:** `apps/backend/archivum/capture/importers/claude_code.py`,
`apps/backend/tests/fixtures/claude_code_session.jsonl`,
`apps/backend/tests/capture/test_claude_code_importer.py`

**Interfaces:** `ClaudeCodeImporter` implementing `ImportConnector`,
`interface="claude_code_import"`, `can_handle` = `.jsonl` suffix. `parse` reads one JSON
object per line (Claude Code session format: each line has `type` ∈
{`user`,`assistant`,`summary`}, `message.role`, `message.content` as a block list) and
builds one `Conversation` per file, `session_id` from the file stem or a `sessionId`
field.

Steps:

- [ ] Create `tests/fixtures/claude_code_session.jsonl` (real 3-line sample):
```
{"type":"user","sessionId":"abc123","timestamp":"2026-07-28T00:00:00Z","message":{"role":"user","content":[{"type":"text","text":"add pytest config"}]}}
{"type":"assistant","sessionId":"abc123","timestamp":"2026-07-28T00:00:02Z","message":{"role":"assistant","content":[{"type":"thinking","thinking":"internal plan the user must never see"},{"type":"text","text":"Adding pytest config now."},{"type":"tool_use","id":"t1","name":"Edit","input":{"path":"pyproject.toml"}}]}}
{"type":"user","sessionId":"abc123","timestamp":"2026-07-28T00:00:03Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"file updated"}]}}
```
- [ ] Write `tests/capture/test_claude_code_importer.py`:
```python
from pathlib import Path

from archivum.capture.importers.claude_code import ClaudeCodeImporter

FIX = Path(__file__).parent.parent / "fixtures" / "claude_code_session.jsonl"


def test_parses_turns_tool_calls_and_session_id():
    res = ClaudeCodeImporter().parse(FIX)
    assert res.interface == "claude_code_import"
    conv = res.conversations[0]
    assert conv.session_id == "abc123"
    assert conv.turns[0].text == "add pytest config"
    # tool_use folded onto assistant turn
    assert conv.turns[1].tool_calls[0].name == "Edit"


def test_can_handle_jsonl():
    assert ClaudeCodeImporter().can_handle(Path("s.jsonl")) is True
    assert ClaudeCodeImporter().can_handle(Path("s.json")) is False
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_claude_code_importer.py -q` — expect **FAIL**.
- [ ] Implement `ClaudeCodeImporter.parse`: iterate lines, `json.loads` each; skip
  `type=="summary"`; use `visible_text_from_blocks` (Task 2) for turn text; collect
  `tool_use` blocks into `ToolCall(name, arguments=input, result=None, call_id=id)` and
  attach to the assistant turn; match later `tool_result` blocks by `tool_use_id` to fill
  `result`. Build one `Conversation` with `origin_uri=str(path)`.
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_claude_code_importer.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/importers/claude_code.py apps/backend/tests/fixtures/claude_code_session.jsonl apps/backend/tests/capture/test_claude_code_importer.py && git commit -m "feat(capture): Claude Code JSONL transcript importer"`

---

### Task 10 — Claude Code importer strips hidden reasoning (end-to-end)

**Files:** `apps/backend/tests/capture/test_claude_code_importer.py` (append)

**Interfaces:** none new; proves the fixture's `thinking` block never reaches a captured
`Conversation` nor L0/L1.

Steps:

- [ ] Append test:
```python
import pytest

from archivum.capture.store import CaptureStore, _SqliteSourceStore
from archivum.db import capture_sql


def test_no_thinking_in_parsed_turns():
    conv = ClaudeCodeImporter().parse(FIX).conversations[0]
    joined = " ".join(t.text for t in conv.turns)
    assert "internal plan" not in joined


@pytest.mark.asyncio
async def test_no_thinking_persisted_to_document(initialized_db):
    conv = ClaudeCodeImporter().parse(FIX).conversations[0]
    res = await CaptureStore(_SqliteSourceStore()).capture(conv)
    doc = await capture_sql.get_document_by_source(res.source_id)
    assert "internal plan" not in doc["text"]
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_claude_code_importer.py -q` — expect **PASS** (redaction from Task 2 already active). If FAIL, fix the importer to route all text through `visible_text_from_blocks`.
- [ ] Commit: `git add apps/backend/tests/capture/test_claude_code_importer.py && git commit -m "test(capture): prove Claude Code import strips hidden reasoning end-to-end"`

---

### Task 11 — Third-party importer: ChatGPT export

**Files:** `apps/backend/archivum/capture/importers/chatgpt.py`,
`apps/backend/tests/fixtures/chatgpt_export.json`,
`apps/backend/tests/capture/test_chatgpt_importer.py`

**Interfaces:** `ChatGptImporter` implementing `ImportConnector`,
`interface="chatgpt_import"`, `can_handle` = `.json` file whose top level is a list of
conversation objects with a `mapping` field. `parse` walks each conversation's `mapping`
node tree in `create_time` order, emitting a `Conversation` per top-level export entry;
ChatGPT reasoning/`thoughts` message parts are dropped via redaction.

Steps:

- [ ] Create `tests/fixtures/chatgpt_export.json` (real minimal export):
```json
[
  {
    "title": "SQLite question",
    "create_time": 1753660800,
    "mapping": {
      "n1": {"id": "n1", "message": {"author": {"role": "user"}, "create_time": 1753660800, "content": {"content_type": "text", "parts": ["is sqlite good for this?"]}}},
      "n2": {"id": "n2", "message": {"author": {"role": "assistant"}, "create_time": 1753660805, "content": {"content_type": "text", "parts": ["Yes, SQLite fits a single-owner store."]}}},
      "n3": {"id": "n3", "message": {"author": {"role": "assistant"}, "create_time": 1753660803, "content": {"content_type": "thoughts", "parts": ["hidden reasoning here"]}}}
    }
  }
]
```
- [ ] Write `tests/capture/test_chatgpt_importer.py`:
```python
from pathlib import Path

from archivum.capture.importers.chatgpt import ChatGptImporter

FIX = Path(__file__).parent.parent / "fixtures" / "chatgpt_export.json"


def test_parses_conversation_in_time_order_without_reasoning():
    res = ChatGptImporter().parse(FIX)
    conv = res.conversations[0]
    texts = [t.text for t in conv.turns]
    assert texts[0] == "is sqlite good for this?"
    assert any("SQLite fits" in t for t in texts)
    assert all("hidden reasoning" not in t for t in texts)
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_chatgpt_importer.py -q` — expect **FAIL**.
- [ ] Implement `ChatGptImporter.parse`: `json.loads` file; for each entry, collect nodes
  with a `message`, drop `content_type=="thoughts"` (and any part in
  `HIDDEN_BLOCK_TYPES`), sort by `create_time`, map `author.role` → `Role`, join
  `content.parts` and run through `redact_turn_text`. `session_id` = entry `title` +
  `create_time`.
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_chatgpt_importer.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/importers/chatgpt.py apps/backend/tests/fixtures/chatgpt_export.json apps/backend/tests/capture/test_chatgpt_importer.py && git commit -m "feat(capture): ChatGPT export importer"`

---

### Task 12 — Provenance: Events, Claims, and session→Source link

**Files:** `apps/backend/archivum/capture/provenance.py`,
`apps/backend/archivum/capture/store.py` (call site),
`apps/backend/tests/capture/test_provenance_events.py`

**Interfaces:**
```python
# provenance.py
async def emit_knowledge(conv: Conversation, capture: CaptureResult) -> ProvenanceResult

@dataclass(frozen=True)
class ProvenanceResult:
    event_ids: tuple[int, ...]
    claim_ids: tuple[int, ...]
```
Rules (spec §4/§5): one `Event(kind="session")` on the first chunk; one
`Event(kind="tool_call")` per `ToolCall` (extraction_method `EXTRACTED`, confidence
`1.0`); one `Claim` per `Decision` (extraction_method `INFERRED`, confidence `0.7`,
`valid_from=conv.started_at`) anchored to the chunk of its `turn_index`; one
`Event(kind="outcome")` per `Outcome`. Every row carries a real `chunk_id` (provenance
invariant). `CaptureStore.capture` calls `emit_knowledge` after inserting chunks (skip on
dedup no-op — knowledge already exists).

Steps:

- [ ] Write `tests/capture/test_provenance_events.py`:
```python
import pytest

from archivum.capture.schema import Conversation, Turn, ToolCall, Decision
from archivum.capture.store import CaptureStore, _SqliteSourceStore
from archivum.db import capture_sql


def _conv():
    tc = ToolCall(name="Edit", arguments={"p": "/a"}, result="ok")
    return Conversation(
        session_id="s1", interface="claude_code_native",
        started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="do X", ts="2026-07-28T00:00:00Z"),
               Turn(role="assistant", text="done", ts="2026-07-28T00:00:01Z",
                    tool_calls=(tc,))),
        decisions=(Decision(statement="use sqlite", rationale="simple", turn_index=1),),
    )


@pytest.mark.asyncio
async def test_emits_events_and_claims_with_provenance(initialized_db):
    res = await CaptureStore(_SqliteSourceStore()).capture(_conv())
    events = await capture_sql.list_events_for_source(res.source_id)
    kinds = {e["kind"] for e in events}
    assert {"session", "tool_call"} <= kinds
    assert all(e["chunk_id"] for e in events)         # provenance invariant
    assert all(e["extraction_method"] in
               {"EXTRACTED", "INFERRED", "AMBIGUOUS"} for e in events)
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_provenance_events.py -q` — expect **FAIL**.
- [ ] Implement `provenance.py` per rules; wire the call in `CaptureStore.capture` guarded
  by `if stored.created:`. Add `list_events_for_source` join (events→chunks→documents→
  source) in `capture_sql` if not already present.
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_provenance_events.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/archivum/capture/provenance.py apps/backend/archivum/capture/store.py apps/backend/archivum/db/capture_sql.py apps/backend/tests/capture/test_provenance_events.py && git commit -m "feat(capture): emit events/claims with provenance linking session to source"`

---

### Task 13 — Idempotent re-import across a full round-trip

**Files:** `apps/backend/tests/capture/test_idempotency.py`

**Interfaces:** none new; proves parse→capture twice for the same file yields no duplicate
sources, documents, chunks, or events.

Steps:

- [ ] Write `tests/capture/test_idempotency.py`:
```python
from pathlib import Path

import pytest

from archivum.capture.importers.claude_code import ClaudeCodeImporter
from archivum.capture.store import CaptureStore, _SqliteSourceStore
from archivum.db.sqlite import get_db

FIX = Path(__file__).parent.parent / "fixtures" / "claude_code_session.jsonl"


async def _counts():
    async with get_db() as db:
        out = {}
        for t in ("sources", "documents", "chunks", "events"):
            async with db.execute(f"SELECT COUNT(*) AS n FROM {t}") as cur:
                out[t] = (await cur.fetchone())["n"]
        return out


@pytest.mark.asyncio
async def test_reimport_is_a_noop(initialized_db):
    store = CaptureStore(_SqliteSourceStore())
    conv = ClaudeCodeImporter().parse(FIX).conversations[0]
    await store.capture(conv)
    first = await _counts()
    await store.capture(ClaudeCodeImporter().parse(FIX).conversations[0])
    assert await _counts() == first
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_idempotency.py -q` — expect **PASS** (Tasks 6 & 12 guarantee this). If FAIL, the dedup guard in Task 6 or the `if stored.created` guard in Task 12 is wrong — fix there.
- [ ] Commit: `git add apps/backend/tests/capture/test_idempotency.py && git commit -m "test(capture): idempotent re-import produces no duplicates"`

---

### Task 14 — Global no-hidden-reasoning guarantee (cross-source)

**Files:** `apps/backend/tests/capture/test_no_hidden_reasoning.py`

**Interfaces:** none new; a leakage guard spanning native + both importers, asserting no
hidden marker ever reaches L1 `documents`, `chunks` text-hash provenance, or `events`.

Steps:

- [ ] Write `tests/capture/test_no_hidden_reasoning.py`:
```python
from pathlib import Path

import pytest

from archivum.capture.importers.claude_code import ClaudeCodeImporter
from archivum.capture.importers.chatgpt import ChatGptImporter
from archivum.capture.native import NativeCaptureWriter
from archivum.capture.store import CaptureStore, _SqliteSourceStore
from archivum.db.sqlite import get_db

FIXDIR = Path(__file__).parent.parent / "fixtures"
SECRETS = ("internal plan", "hidden reasoning", "secret chain")


async def _all_text():
    async with get_db() as db:
        async with db.execute("SELECT text FROM documents") as cur:
            docs = " ".join(r["text"] for r in await cur.fetchall())
        async with db.execute("SELECT summary FROM events") as cur:
            evs = " ".join(r["summary"] for r in await cur.fetchall())
    return docs + " " + evs


@pytest.mark.asyncio
async def test_no_hidden_reasoning_from_any_source(initialized_db):
    store = CaptureStore(_SqliteSourceStore())
    await store.capture(ClaudeCodeImporter().parse(FIXDIR / "claude_code_session.jsonl").conversations[0])
    await store.capture(ChatGptImporter().parse(FIXDIR / "chatgpt_export.json").conversations[0])
    w = NativeCaptureWriter(store, session_id="native1")
    w.record_turn("assistant", "<thinking>secret chain</thinking> ok")
    await w.flush()
    corpus = await _all_text()
    for s in SECRETS:
        assert s not in corpus
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_no_hidden_reasoning.py -q` — expect **PASS**.
- [ ] Commit: `git add apps/backend/tests/capture/test_no_hidden_reasoning.py && git commit -m "test(capture): assert no hidden reasoning leaks from any capture source"`

---

### Task 15 — MCP tool: capture_conversation

**Files:** `apps/backend/archivum/mcp/server.py` (edit),
`apps/backend/tests/capture/test_mcp_capture.py`

**Interfaces:** register an MCP tool `capture_conversation(session_id: str, interface: str,
turns: list[dict], scope: str = "personal") -> dict` where each turn dict is
`{"role","text","ts?","tool_calls?"}`. Builds a `Conversation` (redaction applies), calls
`CaptureStore.capture` + `emit_knowledge`, returns
`{"source_id","content_hash","created","chunks"}`. This is the agent-facing write path
per spec §1 ("MCP server for agent access (read and write)").

Steps:

- [ ] Read `archivum/mcp/server.py` to match its tool-registration style.
- [ ] Write `tests/capture/test_mcp_capture.py`:
```python
import pytest

from archivum.mcp.server import capture_conversation_impl  # thin testable core


@pytest.mark.asyncio
async def test_capture_conversation_tool_persists(initialized_db):
    out = await capture_conversation_impl(
        session_id="s1", interface="claude_code_native",
        turns=[{"role": "user", "text": "hi"},
               {"role": "assistant", "text": "<thinking>x</thinking> hello"}],
    )
    assert out["created"] is True
    assert out["chunks"] == 2
    assert len(out["content_hash"]) == 64
```
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_mcp_capture.py -q` — expect **FAIL**.
- [ ] Implement `capture_conversation_impl(...)` in `server.py` (build `Turn`s, run
  `CaptureStore(_SqliteSourceStore())` or the wired real store, capture, return dict);
  register it as an MCP `@server.tool` wrapper delegating to the impl.
- [ ] Run: `cd apps/backend && uv run pytest tests/capture/test_mcp_capture.py -q` — expect **PASS**.
- [ ] Run full suite: `cd apps/backend && uv run pytest tests/capture -q` — expect **all PASS**.
- [ ] Commit: `git add apps/backend/archivum/mcp/server.py apps/backend/tests/capture/test_mcp_capture.py && git commit -m "feat(capture): MCP capture_conversation tool"`

---

## Self-Review

**Spec coverage.** §1 no-hidden-reasoning: Tasks 2, 10, 14. §2 L0 content-address /
versioned: Tasks 3, 5, 6 (via `SourceStore`). §4 lineage Source→Document→Chunk: Tasks
4, 5. §4 invariant (≥1 provenance + confidence + extraction_method): Task 12 + assertions
in test. §4 Event/Claim: Task 12. §5 "each agent session captured as a Source": Tasks 5,
7. §5 semantic-cache/idempotent: Tasks 6, 13. §6 immutability (new version, never
overwrite): delegated to `SourceStore.put`, asserted in Task 6. Redaction-before-address:
Task 5 ordering. All eight epic requirements covered: schema (1,4), native writer (7),
Claude Code importer (9,10), connector interface + 2nd importer (8,11), redaction (2),
dedup (6), provenance link (12), no-leak + idempotent tests (13,14).

**Placeholder scan.** No `TODO`/`...`/`pass`-only bodies in shipped code. Every function
in every Interfaces block has a defined signature and a task that implements it. Fixtures
are concrete literal files, not stubs.

**Type consistency.** `Role`, `ExtractionMethod`, `ToolCall`, `Turn`, `Decision`,
`Outcome`, `Conversation` defined once (Task 1) and imported everywhere. `CaptureResult`
(Task 5), `ProvenanceResult` (Task 12), `ImportResult`/`ImportConnector` (Task 8),
`StoredSource`/`SourceStore` (Upstream Deps, adapter in Task 5) each defined exactly once.
`extraction_method` values constrained to the spec set and asserted in Task 12. Every
`Event`/`Claim` insert takes a real `chunk_id` — no orphan knowledge objects.

**Fixed inline:** clarified that conversations bypass PER-315's `ingest_source` and
register Document/Chunk explicitly (Upstream Deps + Task 5), because a conversation's
one-chunk-per-turn layout is capture-specific; and that `metadata` is excluded from the
content hash so incidental import metadata never breaks dedup (Task 3).
