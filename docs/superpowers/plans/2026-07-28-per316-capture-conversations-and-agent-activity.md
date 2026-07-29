# PER-316: Capture AI Conversations & Agent Activity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture any user-visible AI session (native Perceo agent workers + imported third-party transcripts) into the PER-315 immutable store as a `conversation` **Source** (L0) with `Document` → one-`Chunk`-per-turn lineage (L1), content-addressed and idempotent, with hidden model reasoning stripped before hashing.

**Architecture:** A pure `Conversation` value object is the single canonical shape every capture path converges on. `CaptureStore` reuses PER-315's real `SourceStore` + `BlobStore` + hashing/chunking primitives (no new tables, no adapters): it content-addresses the canonical conversation JSON as L0 evidence, then registers `Source`/`Document`/`Chunk` rows in the existing evidence schema. Native capture and third-party importers are thin producers of `Conversation`; the store is the single writer.

**Tech Stack:** Python 3.12 async, `aiosqlite` via `archivum.db.sqlite.get_db`, `pytest`/`pytest-asyncio` (repo `pytest.ini`, `asyncio_mode=auto`, `pythonpath=apps/backend`). Stdlib `json`/`dataclasses`/`datetime`/`hashlib`/`re` only — **no new dependencies**. FastAPI route mirrors `archivum/api/sources.py`; MCP tool mirrors `archivum/mcp/server.py`.

## Global Constraints

Copied verbatim from `docs/superpowers/specs/2026-07-28-archivum-architecture-design.md` (§1 non-goals, §4 invariant, §6 trust invariants). Every task's requirements implicitly include this section.

- **No hidden reasoning.** Only user-visible turns and tool activity are captured. Model `thinking`/`reasoning`/`redacted_thinking` blocks are stripped by the redactor **before** content-addressing and never reach L0, L1, or any index. (spec §1, §5.)
- **Evidence is immutable & versioned.** Re-capturing changed content creates a new `Source` version via PER-315; existing rows and blobs are never mutated. (spec §2, §6.1.)
- **Content-addressed & idempotent.** Identical conversation content → identical `content_hash` → re-capture is a no-op returning the existing rows with `deduplicated=True`. (spec §2, §5.)
- **Evolve in place.** Reuse the existing evidence schema (`sources`/`documents`/`chunks`) and PER-315 modules (`store/blobs.py`, `store/repository.py`, `store/hashing.py`, `store/chunking.py`, `store/models.py`). Add **no** new tables and do **not** modify PER-315 files. (spec §3, §9.)
- **Layer boundary — knowledge objects are OUT OF SCOPE.** PER-316 stops at `Source → Document → Chunk` evidence lineage. `Entity`/`Artifact`/`Event`/`Claim`/`Relationship` extraction belongs to **PER-317** (spec §5 agent-worker stage; PER-317 description). Decisions, tool calls, and outcomes are preserved **inside** the canonical `Conversation` (L0 evidence) and rendered into the transcript so PER-317 can extract them later — this epic creates no event/claim rows.
- **Rebuildable indexes.** Nothing here writes into L2. Conversation chunks feed L2 the same way document chunks do. (spec §6.6.)

## Upstream surface (PER-315, real code — verified)

These already exist on this branch. Reuse them exactly; do not reimplement.

- `archivum.store.models` — frozen dataclasses `Source(id, content_hash, version, source_type, origin_uri, scope, ingested_at, recorded_at, valid_from, valid_to)`, `Document(id, source_id, mime, normalized_hash)`, `Chunk(id, document_id, seq, start_offset, end_offset, text_hash)`; `new_id() -> str` (uuid4 hex — **ids are TEXT, not int**).
- `archivum.store.source_types.SourceType` — enum incl. `CONVERSATION = "conversation"`.
- `archivum.store.repository.SourceStore` (async): `insert_source(Source)`, `insert_document(Document)`, `insert_chunk(Chunk)`, `get_source(id)`, `get_source_by_hash_and_version(content_hash, version)`, `latest_version_for_origin(origin_uri) -> int`, `get_document_for_source(source_id) -> Document | None`, `list_chunks(document_id) -> list[Chunk]`.
- `archivum.store.blobs.BlobStore(root)` — `put(bytes) -> content_hash` (write-once, idempotent), `get(hash) -> bytes`.
- `archivum.store.hashing` — `sha256_bytes(bytes) -> str`, `sha256_text(str) -> str`.
- `archivum.config.Settings` — has `blob_dir: Path`, `db_path: Path`.
- `archivum.db.sqlite.init_db(settings)` — applies `_SCHEMA` **and** `EVIDENCE_SCHEMA` (creates `sources`/`documents`/`chunks`) and calls `configure(settings)`. Test fixtures use `Settings(db_path=tmp/"archivum.db", blob_dir=tmp/"blobs")` then `await sqlite.init_db(settings)` (pattern: `tests/store/test_ingest_e2e.py`).

**Deliberate deviation from the deterministic ingest path:** `store.ingest.ingest_source` re-derives text by re-parsing `origin_uri`, which cannot express a conversation's one-chunk-per-turn layout and requires a real file. Capture therefore reuses the lower-level `SourceStore`/`BlobStore` primitives directly (Task 5) instead of calling `ingest_source`.

## File Structure

```
apps/backend/archivum/capture/
  __init__.py                 # public exports (Task 1)
  schema.py                   # Conversation/Turn/ToolCall/Decision/Outcome (Task 1)
  redaction.py                # strip hidden reasoning (Task 2)
  canonical.py                # deterministic canonical JSON + content_hash (Task 3)
  transcript.py               # Conversation -> transcript text + per-turn spans (Task 4)
  store.py                    # CaptureStore: Conversation -> L0 Source + L1 doc/chunks (Task 5)
  native.py                   # NativeCaptureWriter for agent workers (Task 6)
  importers/
    __init__.py               # connector registry (Task 7)
    base.py                   # ImportConnector protocol + ImportResult (Task 7)
    claude_code.py            # Claude Code JSONL transcript importer (Task 8)
    chatgpt.py                # ChatGPT export importer (Task 9)
apps/backend/archivum/api/capture.py   # REST: /api/sources/capture[/import] (Task 10)
apps/backend/archivum/api/__init__... n/a
apps/backend/archivum/main.py          # mount capture router (Task 10, edit)
apps/backend/archivum/mcp/server.py    # capture_conversation MCP tool (Task 11, edit)
tests/capture/
  __init__.py
  test_schema.py              # Task 1
  test_redaction.py           # Task 2
  test_canonical.py           # Task 3
  test_transcript.py          # Task 4
  test_store.py               # Tasks 5
  test_native.py              # Task 6
  test_importer_base.py       # Task 7
  test_claude_code_importer.py# Task 8
  test_chatgpt_importer.py    # Task 9
  test_capture_api.py         # Task 10
  test_mcp_capture.py         # Task 11
  test_integration.py         # Task 12 (idempotency + no-hidden-reasoning)
tests/fixtures/capture/
  claude_code_session.jsonl   # Task 8
  chatgpt_export.json         # Task 9
```

No `tests/capture/conftest.py` and no pytest-config task are needed — `pytest.ini` already sets `asyncio_mode=auto` and `pythonpath=apps/backend`. Each async test builds its own tmp `Settings` + `init_db` inline (repo idiom).

---

### Task 1: Canonical conversation schema

**Files:**
- Create: `apps/backend/archivum/capture/schema.py`
- Create: `apps/backend/archivum/capture/__init__.py`
- Test: `tests/capture/__init__.py`, `tests/capture/test_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: frozen dataclasses `ToolCall`, `Turn`, `Decision`, `Outcome`, `Conversation` and aliases `Role`, `ExtractionMethod`. Exact fields below — every later task imports these names.

- [ ] **Step 1: Create empty test package file** `tests/capture/__init__.py` (empty).

- [ ] **Step 2: Write the failing test** — `tests/capture/test_schema.py`

```python
import dataclasses

from archivum.capture.schema import Conversation, ToolCall, Turn


def test_conversation_is_frozen_and_nests_tool_calls():
    tc = ToolCall(name="Read", arguments={"path": "/x"}, result="ok")
    turn = Turn(role="assistant", text="reading", ts="2026-07-28T00:00:00Z", tool_calls=(tc,))
    conv = Conversation(
        session_id="s1", interface="claude_code_native",
        started_at="2026-07-28T00:00:00Z", turns=(turn,),
    )
    assert conv.turns[0].tool_calls[0].name == "Read"
    assert conv.turns[0].tool_calls[0].ok is True
    assert conv.scope == "personal"
    with dataclasses.FrozenInstanceError if False else _expect_frozen():
        pass


import contextlib


@contextlib.contextmanager
def _expect_frozen():
    yield


def test_frozen_assignment_raises():
    conv = Conversation(session_id="s1", interface="x", started_at="t", turns=())
    try:
        conv.session_id = "s2"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        return
    raise AssertionError("Conversation should be frozen")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_schema.py -q`
Expected: FAIL — `ModuleNotFoundError: archivum.capture.schema`.

- [ ] **Step 4: Write minimal implementation** — `apps/backend/archivum/capture/schema.py`

```python
"""Canonical conversation value objects — the single shape every capture path
converges on. User-visible content only (redaction happens upstream)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "assistant", "tool", "system"]
ExtractionMethod = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: str | None = None
    call_id: str | None = None
    started_at: str | None = None
    ok: bool = True


@dataclass(frozen=True, slots=True)
class Turn:
    role: Role
    text: str
    ts: str = ""
    tool_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class Decision:
    statement: str
    rationale: str = ""
    turn_index: int = -1


@dataclass(frozen=True, slots=True)
class Outcome:
    task: str
    status: Literal["success", "failure", "partial", "unknown"] = "unknown"
    detail: str = ""
    turn_index: int = -1


@dataclass(frozen=True, slots=True)
class Conversation:
    session_id: str
    interface: str
    started_at: str
    turns: tuple[Turn, ...]
    decisions: tuple[Decision, ...] = ()
    outcomes: tuple[Outcome, ...] = ()
    scope: str = "personal"
    origin_uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
```

- [ ] **Step 5: Write** `apps/backend/archivum/capture/__init__.py`

```python
"""Archivum capture layer (PER-316): AI sessions -> immutable Sources."""

from archivum.capture.schema import (
    Conversation,
    Decision,
    Outcome,
    Role,
    ToolCall,
    Turn,
)

__all__ = ["Conversation", "Turn", "ToolCall", "Decision", "Outcome", "Role"]
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_schema.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/archivum/capture/__init__.py apps/backend/archivum/capture/schema.py tests/capture/__init__.py tests/capture/test_schema.py
git commit -m "feat(capture): canonical conversation schema"
```

---

### Task 2: Redaction — strip hidden model reasoning

**Files:**
- Create: `apps/backend/archivum/capture/redaction.py`
- Test: `tests/capture/test_redaction.py`

**Interfaces:**
- Consumes: raw provider content (a `str` or a list of provider content-block dicts).
- Produces: `HIDDEN_BLOCK_TYPES: frozenset[str]`; `redact_turn_text(text: str) -> str`; `visible_text_from_blocks(content: Any) -> str`.

- [ ] **Step 1: Write the failing test** — `tests/capture/test_redaction.py`

```python
from archivum.capture.redaction import redact_turn_text, visible_text_from_blocks


def test_drops_thinking_blocks_keeps_text_and_tool_result():
    blocks = [
        {"type": "thinking", "thinking": "secret chain of thought"},
        {"type": "text", "text": "here is the answer"},
        {"type": "tool_result", "content": "file updated"},
    ]
    out = visible_text_from_blocks(blocks)
    assert "secret" not in out
    assert "here is the answer" in out
    assert "file updated" in out


def test_redacts_inline_reasoning_tags():
    assert "secret" not in redact_turn_text("a <thinking>secret</thinking> b")
    assert "why" not in redact_turn_text("x <reasoning>why</reasoning> y")


def test_plain_string_passthrough():
    assert visible_text_from_blocks("hello") == "hello"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_redaction.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `apps/backend/archivum/capture/redaction.py`

```python
"""Strip hidden model reasoning before anything is content-addressed (spec §1)."""

from __future__ import annotations

import re
from typing import Any

HIDDEN_BLOCK_TYPES: frozenset[str] = frozenset(
    {"thinking", "reasoning", "redacted_thinking", "thoughts"}
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

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_redaction.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/capture/redaction.py tests/capture/test_redaction.py
git commit -m "feat(capture): redaction strips hidden model reasoning"
```

---

### Task 3: Canonical JSON & content hashing

**Files:**
- Create: `apps/backend/archivum/capture/canonical.py`
- Test: `tests/capture/test_canonical.py`

**Interfaces:**
- Consumes: `Conversation` (Task 1); `sha256_bytes` (PER-315).
- Produces: `to_canonical_dict(conv) -> dict`; `to_canonical_bytes(conv) -> bytes`; `content_hash(conv) -> str`. Determinism rule: identical conversation content → identical bytes → identical 64-char hex hash. `metadata` is transport-only and excluded from identity so incidental import metadata never breaks dedup.

- [ ] **Step 1: Write the failing test** — `tests/capture/test_canonical.py`

```python
from archivum.capture.canonical import content_hash, to_canonical_bytes
from archivum.capture.schema import Conversation, Turn
from archivum.store.hashing import sha256_bytes


def _conv(meta):
    return Conversation(
        session_id="s1", interface="x", started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="hi", ts="2026-07-28T00:00:00Z"),),
        metadata=meta,
    )


def test_hash_is_stable_ignores_metadata_and_matches_sha256_of_bytes():
    a = content_hash(_conv({"a": 1}))
    b = content_hash(_conv({"b": 2}))
    assert a == b and len(a) == 64
    assert a == sha256_bytes(to_canonical_bytes(_conv({"a": 1})))


def test_bytes_are_sorted_compact_json():
    raw = to_canonical_bytes(_conv({}))
    assert raw.startswith(b"{") and b'"interface"' in raw
    assert b'"metadata"' not in raw
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_canonical.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `apps/backend/archivum/capture/canonical.py`

```python
"""Deterministic canonical JSON for a Conversation + its content hash (L0 key)."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from archivum.capture.schema import Conversation
from archivum.store.hashing import sha256_bytes


def to_canonical_dict(conv: Conversation) -> dict[str, Any]:
    d = dataclasses.asdict(conv)
    d.pop("metadata", None)  # transport-only, excluded from identity
    return d


def to_canonical_bytes(conv: Conversation) -> bytes:
    return json.dumps(
        to_canonical_dict(conv),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_hash(conv: Conversation) -> str:
    return sha256_bytes(to_canonical_bytes(conv))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_canonical.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/capture/canonical.py tests/capture/test_canonical.py
git commit -m "feat(capture): deterministic canonical json + content hash"
```

---

### Task 4: Transcript rendering (one span per turn)

**Files:**
- Create: `apps/backend/archivum/capture/transcript.py`
- Test: `tests/capture/test_transcript.py`

**Interfaces:**
- Consumes: `Conversation`, `Turn`, `ToolCall` (Task 1).
- Produces: `TurnSpan = tuple[int, int, str]` (start_offset, end_offset, block_text) and `render_transcript(conv) -> tuple[str, list[TurnSpan]]`. Invariant: `text[start:end] == block_text` for every span, one span per turn, in order. Tool calls are rendered into their turn's block so tool activity survives in L0/L1 evidence for PER-317.

- [ ] **Step 1: Write the failing test** — `tests/capture/test_transcript.py`

```python
from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.capture.transcript import render_transcript


def _conv():
    tc = ToolCall(name="Edit", arguments={"path": "/a.py"}, result="written")
    return Conversation(
        session_id="s1", interface="x", started_at="t",
        turns=(
            Turn(role="user", text="do X", ts="t"),
            Turn(role="assistant", text="did X", ts="t", tool_calls=(tc,)),
        ),
    )


def test_one_span_per_turn_and_offsets_are_exact():
    text, spans = render_transcript(_conv())
    assert len(spans) == 2
    for start, end, block in spans:
        assert text[start:end] == block
    assert "[user] do X" in spans[0][2]
    assert "Edit" in spans[1][2] and "written" in spans[1][2]


def test_empty_conversation_renders_empty():
    conv = Conversation(session_id="s", interface="x", started_at="t", turns=())
    text, spans = render_transcript(conv)
    assert text == "" and spans == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_transcript.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `apps/backend/archivum/capture/transcript.py`

```python
"""Render a Conversation into a stable human-readable transcript plus the
character span of each turn, used as the L1 Document text and chunk anchors."""

from __future__ import annotations

import json

from archivum.capture.schema import Conversation, ToolCall, Turn

TurnSpan = tuple[int, int, str]

_SEP = "\n\n"


def _render_tool_call(tc: ToolCall) -> str:
    args = json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False)
    status = "" if tc.ok else " [error]"
    result = "" if tc.result is None else f" -> {tc.result}"
    return f"  ↳ {tc.name}({args}){status}{result}"


def _render_turn(turn: Turn) -> str:
    lines = [f"[{turn.role}] {turn.text}".rstrip()]
    lines.extend(_render_tool_call(tc) for tc in turn.tool_calls)
    return "\n".join(lines)


def render_transcript(conv: Conversation) -> tuple[str, list[TurnSpan]]:
    blocks = [_render_turn(t) for t in conv.turns]
    text = _SEP.join(blocks)
    spans: list[TurnSpan] = []
    cursor = 0
    for block in blocks:
        start = cursor
        end = start + len(block)
        spans.append((start, end, block))
        cursor = end + len(_SEP)
    return text, spans
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_transcript.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/capture/transcript.py tests/capture/test_transcript.py
git commit -m "feat(capture): deterministic transcript rendering with per-turn spans"
```

---

### Task 5: CaptureStore — Conversation → L0 Source + L1 Document/Chunks

**Files:**
- Create: `apps/backend/archivum/capture/store.py`
- Test: `tests/capture/test_store.py`

**Interfaces:**
- Consumes: `Conversation` (Task 1); `content_hash`/`to_canonical_bytes` (Task 3); `render_transcript` (Task 4); PER-315 `SourceStore`, `BlobStore`, `Source`/`Document`/`Chunk`/`new_id`, `SourceType.CONVERSATION`, `sha256_text`, `Settings`.
- Produces:
```python
@dataclass(frozen=True, slots=True)
class CaptureResult:
    source_id: str
    content_hash: str
    version: int
    document_id: str
    chunk_ids: tuple[str, ...]
    deduplicated: bool

class CaptureStore:
    def __init__(self, *, store: SourceStore | None = None,
                 blob_store: BlobStore | None = None,
                 settings: Settings | None = None) -> None: ...
    async def capture(self, conv: Conversation) -> CaptureResult: ...
```
Behavior: `origin = conv.origin_uri or f"conversation:{conv.interface}:{conv.session_id}"`. Dedup per `(origin, content_hash)` (mirrors `store.ingest._existing_version` using only public `SourceStore` methods). On dedup hit → return existing rows, `deduplicated=True`, no writes. Else `blob_store.put(canonical_bytes)` (L0), then insert one `Source(source_type=CONVERSATION, version=latest+1)`, one `Document(mime="text/plain", normalized_hash=sha256_text(transcript))`, and one `Chunk` per turn span.

- [ ] **Step 1: Write the failing test** — `tests/capture/test_store.py`

```python
import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.capture.store import CaptureResult, CaptureStore
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return CaptureStore(store=SourceStore(), blob_store=BlobStore(settings.blob_dir),
                        settings=settings)


def _conv():
    tc = ToolCall(name="Edit", arguments={"p": "/a"}, result="written")
    return Conversation(
        session_id="s1", interface="claude_code_native", started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="do X", ts="t"),
               Turn(role="assistant", text="did X", ts="t", tool_calls=(tc,))),
    )


@pytest.mark.asyncio
async def test_capture_writes_source_document_and_chunk_per_turn(env):
    res = await env.capture(_conv())
    assert isinstance(res, CaptureResult)
    assert res.deduplicated is False
    assert res.version == 1
    assert len(res.chunk_ids) == 2
    assert len(res.content_hash) == 64

    store = SourceStore()
    source = await store.get_source(res.source_id)
    assert source is not None and source.source_type.value == "conversation"
    document = await store.get_document_for_source(res.source_id)
    assert document is not None and document.mime == "text/plain"


@pytest.mark.asyncio
async def test_recapture_identical_content_is_dedup_noop(env):
    r1 = await env.capture(_conv())
    r2 = await env.capture(_conv())
    assert r2.deduplicated is True
    assert r2.source_id == r1.source_id
    assert r2.chunk_ids == r1.chunk_ids

    async with __import__("archivum.db.sqlite", fromlist=["get_db"]).get_db() as db:
        async with db.execute("SELECT COUNT(*) AS n FROM chunks") as cur:
            n = (await cur.fetchone())["n"]
    assert n == 2  # not duplicated


@pytest.mark.asyncio
async def test_changed_content_creates_v2_without_mutating_v1(env):
    r1 = await env.capture(_conv())
    changed = Conversation(
        session_id="s1", interface="claude_code_native", started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="do Y", ts="t"),),
    )
    r2 = await env.capture(changed)
    assert (r1.version, r2.version) == (1, 2)
    assert r1.content_hash != r2.content_hash
    assert r2.source_id != r1.source_id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_store.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `apps/backend/archivum/capture/store.py`

```python
"""CaptureStore: write a Conversation to L0 (content-addressed evidence) and
L1 (Source -> Document -> one Chunk per turn) reusing PER-315 primitives.
Idempotent per (origin, content_hash); never mutates existing rows/blobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from archivum.capture.canonical import content_hash, to_canonical_bytes
from archivum.capture.schema import Conversation
from archivum.capture.transcript import render_transcript
from archivum.config import Settings, get_settings
from archivum.store.blobs import BlobStore
from archivum.store.hashing import sha256_text
from archivum.store.models import Chunk, Document, Source, new_id
from archivum.store.repository import SourceStore
from archivum.store.source_types import SourceType


@dataclass(frozen=True, slots=True)
class CaptureResult:
    source_id: str
    content_hash: str
    version: int
    document_id: str
    chunk_ids: tuple[str, ...]
    deduplicated: bool


class CaptureStore:
    def __init__(
        self,
        *,
        store: SourceStore | None = None,
        blob_store: BlobStore | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._store = store or SourceStore()
        self._blobs = blob_store or BlobStore(self._settings.blob_dir)

    async def capture(self, conv: Conversation) -> CaptureResult:
        raw = to_canonical_bytes(conv)
        chash = content_hash(conv)
        origin = conv.origin_uri or f"conversation:{conv.interface}:{conv.session_id}"

        existing = await self._existing(origin, chash)
        if existing is not None:
            document = await self._store.get_document_for_source(existing.id)
            assert document is not None
            chunks = await self._store.list_chunks(document.id)
            return CaptureResult(
                source_id=existing.id, content_hash=chash, version=existing.version,
                document_id=document.id, chunk_ids=tuple(c.id for c in chunks),
                deduplicated=True,
            )

        version = await self._store.latest_version_for_origin(origin) + 1
        self._blobs.put(raw)  # L0 evidence, write-once

        text, spans = render_transcript(conv)
        now = datetime.now(UTC).isoformat()
        source = Source(
            id=new_id(), content_hash=chash, version=version,
            source_type=SourceType.CONVERSATION, origin_uri=origin, scope=conv.scope,
            ingested_at=now, recorded_at=now, valid_from=conv.started_at or now,
            valid_to=None,
        )
        await self._store.insert_source(source)

        document = Document(
            id=new_id(), source_id=source.id, mime="text/plain",
            normalized_hash=sha256_text(text),
        )
        await self._store.insert_document(document)

        chunk_ids: list[str] = []
        for seq, (start, end, block) in enumerate(spans):
            chunk = Chunk(
                id=new_id(), document_id=document.id, seq=seq,
                start_offset=start, end_offset=end, text_hash=sha256_text(block),
            )
            await self._store.insert_chunk(chunk)
            chunk_ids.append(chunk.id)

        return CaptureResult(
            source_id=source.id, content_hash=chash, version=version,
            document_id=document.id, chunk_ids=tuple(chunk_ids), deduplicated=False,
        )

    async def _existing(self, origin: str, chash: str) -> Source | None:
        latest = await self._store.latest_version_for_origin(origin)
        for version in range(1, latest + 1):
            match = await self._store.get_source_by_hash_and_version(chash, version)
            if match is not None and match.origin_uri == origin:
                return match
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_store.py -q`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/capture/store.py tests/capture/test_store.py
git commit -m "feat(capture): CaptureStore writes conversation to L0 source + L1 doc/chunks"
```

---

### Task 6: Native capture writer for agent workers

**Files:**
- Create: `apps/backend/archivum/capture/native.py`
- Test: `tests/capture/test_native.py`

**Interfaces:**
- Consumes: `CaptureStore` (Task 5); `Conversation`/`Turn`/`ToolCall`/`Decision`/`Outcome`/`Role` (Task 1); `redact_turn_text` (Task 2).
- Produces:
```python
class NativeCaptureWriter:
    def __init__(self, store: CaptureStore, *, session_id: str,
                 interface: str = "claude_code_native", scope: str = "personal",
                 origin_uri: str = "") -> None: ...
    def record_turn(self, role: Role, text: str,
                    tool_calls: Sequence[ToolCall] = ()) -> None: ...
    def record_tool_call(self, name: str, arguments: dict, result: str | None = None,
                         ok: bool = True) -> None: ...   # attaches to last turn
    def record_decision(self, statement: str, rationale: str = "") -> None: ...
    def record_outcome(self, task: str, status: str = "unknown", detail: str = "") -> None: ...
    def build(self) -> Conversation: ...
    async def flush(self) -> CaptureResult: ...
```
Text is routed through `redact_turn_text` on the way in, so hidden reasoning never enters the buffer. Timestamps default to `datetime.now(UTC).isoformat()`.

- [ ] **Step 1: Write the failing test** — `tests/capture/test_native.py`

```python
import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.capture.native import NativeCaptureWriter
from archivum.capture.store import CaptureStore
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore


@pytest.fixture
async def store(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return CaptureStore(store=SourceStore(), blob_store=BlobStore(settings.blob_dir),
                        settings=settings)


@pytest.mark.asyncio
async def test_native_writer_redacts_records_and_flushes(store):
    w = NativeCaptureWriter(store, session_id="s1")
    w.record_turn("user", "add a feature")
    w.record_turn("assistant", "<thinking>hidden</thinking> on it")
    w.record_tool_call("Edit", {"path": "/a.py"}, "written")
    w.record_decision("use dataclasses", "simpler")
    w.record_outcome("add feature", "success")

    conv = w.build()
    assert "hidden" not in conv.turns[1].text
    assert conv.turns[1].tool_calls[0].name == "Edit"
    assert conv.decisions[0].statement == "use dataclasses"
    assert conv.outcomes[0].status == "success"

    res = await w.flush()
    assert res.deduplicated is False
    assert len(res.chunk_ids) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_native.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write minimal implementation** — `apps/backend/archivum/capture/native.py`

```python
"""Live capture writer for Perceo-controlled agent workers. Buffers redacted
turns/tool-calls/decisions/outcomes, then flushes one Conversation to the store."""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from datetime import UTC, datetime

from archivum.capture.redaction import redact_turn_text
from archivum.capture.schema import (
    Conversation,
    Decision,
    Outcome,
    Role,
    ToolCall,
    Turn,
)
from archivum.capture.store import CaptureResult, CaptureStore


def _now() -> str:
    return datetime.now(UTC).isoformat()


class NativeCaptureWriter:
    def __init__(
        self,
        store: CaptureStore,
        *,
        session_id: str,
        interface: str = "claude_code_native",
        scope: str = "personal",
        origin_uri: str = "",
    ) -> None:
        self._store = store
        self._session_id = session_id
        self._interface = interface
        self._scope = scope
        self._origin_uri = origin_uri
        self._started_at = _now()
        self._turns: list[Turn] = []
        self._decisions: list[Decision] = []
        self._outcomes: list[Outcome] = []

    def record_turn(
        self, role: Role, text: str, tool_calls: Sequence[ToolCall] = ()
    ) -> None:
        self._turns.append(
            Turn(role=role, text=redact_turn_text(text), ts=_now(),
                 tool_calls=tuple(tool_calls))
        )

    def record_tool_call(
        self, name: str, arguments: dict, result: str | None = None, ok: bool = True
    ) -> None:
        tc = ToolCall(
            name=name, arguments=arguments,
            result=None if result is None else redact_turn_text(result),
            started_at=_now(), ok=ok,
        )
        if not self._turns:
            self._turns.append(Turn(role="assistant", text="", ts=_now()))
        last = self._turns[-1]
        self._turns[-1] = dataclasses.replace(last, tool_calls=last.tool_calls + (tc,))

    def record_decision(self, statement: str, rationale: str = "") -> None:
        self._decisions.append(
            Decision(statement=statement, rationale=rationale, turn_index=len(self._turns) - 1)
        )

    def record_outcome(self, task: str, status: str = "unknown", detail: str = "") -> None:
        self._outcomes.append(
            Outcome(task=task, status=status, detail=detail, turn_index=len(self._turns) - 1)  # type: ignore[arg-type]
        )

    def build(self) -> Conversation:
        return Conversation(
            session_id=self._session_id, interface=self._interface,
            started_at=self._started_at, turns=tuple(self._turns),
            decisions=tuple(self._decisions), outcomes=tuple(self._outcomes),
            scope=self._scope, origin_uri=self._origin_uri,
        )

    async def flush(self) -> CaptureResult:
        return await self._store.capture(self.build())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_native.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/capture/native.py tests/capture/test_native.py
git commit -m "feat(capture): native capture writer for agent workers"
```

---

### Task 7: Import connector protocol + registry

**Files:**
- Create: `apps/backend/archivum/capture/importers/base.py`
- Create: `apps/backend/archivum/capture/importers/__init__.py`
- Test: `tests/capture/test_importer_base.py`

**Interfaces:**
- Consumes: `Conversation` (Task 1).
- Produces:
```python
# base.py
@dataclass(frozen=True, slots=True)
class ImportResult:
    conversations: tuple[Conversation, ...]
    interface: str

class ImportConnector(Protocol):
    interface: str
    def can_handle(self, path: Path) -> bool: ...
    def parse(self, path: Path) -> ImportResult: ...

# __init__.py
def register(connector: ImportConnector) -> None
def connector_for(path: Path) -> ImportConnector | None
def all_connectors() -> tuple[ImportConnector, ...]
```
Connectors are pure parsers (no DB); the caller feeds each `Conversation` to `CaptureStore.capture`, so idempotency/dedup (Task 5) apply uniformly to imports. `connector_for` returns the first registered connector whose `can_handle` is True.

- [ ] **Step 1: Write the failing test** — `tests/capture/test_importer_base.py`

```python
from pathlib import Path

from archivum.capture.importers import all_connectors, connector_for, register
from archivum.capture.importers.base import ImportResult


class _Fake:
    interface = "fake"

    def can_handle(self, path):
        return path.suffix == ".fake"

    def parse(self, path):
        return ImportResult(conversations=(), interface="fake")


def test_registry_dispatches_by_can_handle():
    register(_Fake())
    assert connector_for(Path("x.fake")).interface == "fake"
    assert connector_for(Path("x.nope")) is None
    assert any(c.interface == "fake" for c in all_connectors())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_importer_base.py -q`
Expected: FAIL — module missing.

- [ ] **Step 3: Write** `apps/backend/archivum/capture/importers/base.py`

```python
"""Import connector contract: a pure parser from a file to Conversations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from archivum.capture.schema import Conversation


@dataclass(frozen=True, slots=True)
class ImportResult:
    conversations: tuple[Conversation, ...]
    interface: str


@runtime_checkable
class ImportConnector(Protocol):
    interface: str

    def can_handle(self, path: Path) -> bool: ...

    def parse(self, path: Path) -> ImportResult: ...
```

- [ ] **Step 4: Write** `apps/backend/archivum/capture/importers/__init__.py`

```python
"""Connector registry. Built-in connectors self-register on import."""

from __future__ import annotations

from pathlib import Path

from archivum.capture.importers.base import ImportConnector, ImportResult

_REGISTRY: list[ImportConnector] = []


def register(connector: ImportConnector) -> None:
    _REGISTRY.append(connector)


def connector_for(path: Path) -> ImportConnector | None:
    for connector in _REGISTRY:
        if connector.can_handle(path):
            return connector
    return None


def all_connectors() -> tuple[ImportConnector, ...]:
    return tuple(_REGISTRY)


__all__ = [
    "ImportConnector",
    "ImportResult",
    "register",
    "connector_for",
    "all_connectors",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_importer_base.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/capture/importers/__init__.py apps/backend/archivum/capture/importers/base.py tests/capture/test_importer_base.py
git commit -m "feat(capture): import connector protocol + registry"
```

---

### Task 8: Claude Code transcript importer (JSONL)

**Files:**
- Create: `apps/backend/archivum/capture/importers/claude_code.py`
- Create: `tests/fixtures/capture/claude_code_session.jsonl`
- Test: `tests/capture/test_claude_code_importer.py`

**Interfaces:**
- Consumes: `visible_text_from_blocks` (Task 2); `Conversation`/`Turn`/`ToolCall` (Task 1); `ImportResult`/`register` (Task 7).
- Produces: `ClaudeCodeImporter` implementing `ImportConnector`, `interface="claude_code_import"`, `can_handle` = `.jsonl`. `parse` reads one JSON object per line: skip `type=="summary"`; per line build a `Turn` from `message.role` + `visible_text_from_blocks(message.content)`; collect `tool_use` blocks into `ToolCall(name, arguments=input, call_id=id)` attached to that turn; match later `tool_result` blocks by `tool_use_id` to fill `result`. `session_id` from a `sessionId` field (fallback: file stem). One `Conversation` per file, `origin_uri=str(path)`. Registers itself at import time.

- [ ] **Step 1: Create fixture** `tests/fixtures/capture/claude_code_session.jsonl` (exactly three lines)

```
{"type":"user","sessionId":"abc123","timestamp":"2026-07-28T00:00:00Z","message":{"role":"user","content":[{"type":"text","text":"add pytest config"}]}}
{"type":"assistant","sessionId":"abc123","timestamp":"2026-07-28T00:00:02Z","message":{"role":"assistant","content":[{"type":"thinking","thinking":"internal plan the user must never see"},{"type":"text","text":"Adding pytest config now."},{"type":"tool_use","id":"t1","name":"Edit","input":{"path":"pyproject.toml"}}]}}
{"type":"user","sessionId":"abc123","timestamp":"2026-07-28T00:00:03Z","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"file updated"}]}}
```

- [ ] **Step 2: Write the failing test** — `tests/capture/test_claude_code_importer.py`

```python
from pathlib import Path

from archivum.capture.importers.claude_code import ClaudeCodeImporter

FIX = Path(__file__).parent.parent / "fixtures" / "capture" / "claude_code_session.jsonl"


def test_can_handle_jsonl_only():
    imp = ClaudeCodeImporter()
    assert imp.can_handle(Path("s.jsonl")) is True
    assert imp.can_handle(Path("s.json")) is False


def test_parses_turns_tool_calls_and_session_id():
    res = ClaudeCodeImporter().parse(FIX)
    assert res.interface == "claude_code_import"
    conv = res.conversations[0]
    assert conv.session_id == "abc123"
    assert conv.turns[0].text == "add pytest config"
    assert conv.turns[1].tool_calls[0].name == "Edit"
    assert conv.turns[1].tool_calls[0].result == "file updated"


def test_no_thinking_in_parsed_turns():
    conv = ClaudeCodeImporter().parse(FIX).conversations[0]
    joined = " ".join(t.text for t in conv.turns)
    assert "internal plan" not in joined
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_claude_code_importer.py -q`
Expected: FAIL — module missing.

- [ ] **Step 4: Write minimal implementation** — `apps/backend/archivum/capture/importers/claude_code.py`

```python
"""Importer for Claude Code session transcripts (one JSON object per line)."""

from __future__ import annotations

import json
from pathlib import Path

from archivum.capture.importers import register
from archivum.capture.importers.base import ImportResult
from archivum.capture.redaction import visible_text_from_blocks
from archivum.capture.schema import Conversation, ToolCall, Turn

_INTERFACE = "claude_code_import"


class ClaudeCodeImporter:
    interface = _INTERFACE

    def can_handle(self, path: Path) -> bool:
        return path.suffix == ".jsonl"

    def parse(self, path: Path) -> ImportResult:
        session_id = path.stem
        started_at = ""
        turns: list[Turn] = []
        pending: dict[str, ToolCall] = {}  # call_id -> ToolCall awaiting result
        turn_of_call: dict[str, int] = {}  # call_id -> index in `turns`

        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("type") == "summary":
                continue
            session_id = obj.get("sessionId", session_id)
            started_at = started_at or obj.get("timestamp", "")
            message = obj.get("message") or {}
            role = message.get("role", obj.get("type", "user"))
            content = message.get("content", "")

            # Fill any tool_results into the ToolCall they answer, don't emit a turn.
            results = self._tool_results(content)
            if results:
                for call_id, result_text in results.items():
                    call = pending.pop(call_id, None)
                    if call is None:
                        continue
                    idx = turn_of_call.get(call_id)
                    if idx is None:
                        continue
                    filled = ToolCall(
                        name=call.name, arguments=call.arguments, result=result_text,
                        call_id=call.call_id, started_at=call.started_at, ok=call.ok,
                    )
                    turn = turns[idx]
                    turns[idx] = Turn(
                        role=turn.role, text=turn.text, ts=turn.ts,
                        tool_calls=tuple(
                            filled if tc.call_id == call_id else tc for tc in turn.tool_calls
                        ),
                    )
                continue

            calls = self._tool_uses(content)
            text = visible_text_from_blocks(content)
            if not text and not calls:
                continue
            turn = Turn(role=role, text=text, ts=obj.get("timestamp", ""),
                        tool_calls=tuple(calls))
            turns.append(turn)
            for call in calls:
                if call.call_id:
                    pending[call.call_id] = call
                    turn_of_call[call.call_id] = len(turns) - 1

        conv = Conversation(
            session_id=session_id, interface=_INTERFACE,
            started_at=started_at, turns=tuple(turns), origin_uri=str(path),
        )
        return ImportResult(conversations=(conv,), interface=_INTERFACE)

    @staticmethod
    def _tool_uses(content: object) -> list[ToolCall]:
        if not isinstance(content, list):
            return []
        out: list[ToolCall] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.append(ToolCall(
                    name=str(block.get("name", "")),
                    arguments=dict(block.get("input", {})),
                    result=None, call_id=block.get("id"),
                ))
        return out

    @staticmethod
    def _tool_results(content: object) -> dict[str, str]:
        if not isinstance(content, list):
            return {}
        out: dict[str, str] = {}
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                cid = block.get("tool_use_id")
                if cid:
                    out[cid] = str(block.get("content", ""))
        return out


register(ClaudeCodeImporter())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_claude_code_importer.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/capture/importers/claude_code.py tests/fixtures/capture/claude_code_session.jsonl tests/capture/test_claude_code_importer.py
git commit -m "feat(capture): Claude Code JSONL transcript importer"
```

---

### Task 9: Third-party importer — ChatGPT export

**Files:**
- Create: `apps/backend/archivum/capture/importers/chatgpt.py`
- Create: `tests/fixtures/capture/chatgpt_export.json`
- Test: `tests/capture/test_chatgpt_importer.py`

**Interfaces:**
- Consumes: `redact_turn_text`/`HIDDEN_BLOCK_TYPES` (Task 2); `Conversation`/`Turn` (Task 1); `ImportResult`/`register` (Task 7).
- Produces: `ChatGptImporter` implementing `ImportConnector`, `interface="chatgpt_import"`, `can_handle` = `.json` whose top-level parses to a list of objects each having a `mapping` field. `parse` emits one `Conversation` per export entry: collect `mapping` nodes with a `message`, drop `content.content_type` in `HIDDEN_BLOCK_TYPES` (e.g. `thoughts`), sort by `create_time`, map `author.role` → role, join `content.parts` through `redact_turn_text`. `session_id = f"{title}:{create_time}"`.

- [ ] **Step 1: Create fixture** `tests/fixtures/capture/chatgpt_export.json`

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

- [ ] **Step 2: Write the failing test** — `tests/capture/test_chatgpt_importer.py`

```python
from pathlib import Path

from archivum.capture.importers.chatgpt import ChatGptImporter

FIX = Path(__file__).parent.parent / "fixtures" / "capture" / "chatgpt_export.json"


def test_can_handle_json_export():
    assert ChatGptImporter().can_handle(FIX) is True
    assert ChatGptImporter().can_handle(Path("s.jsonl")) is False


def test_parses_in_time_order_without_reasoning():
    conv = ChatGptImporter().parse(FIX).conversations[0]
    texts = [t.text for t in conv.turns]
    assert texts[0] == "is sqlite good for this?"
    assert any("SQLite fits" in t for t in texts)
    assert all("hidden reasoning" not in t for t in texts)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_chatgpt_importer.py -q`
Expected: FAIL — module missing.

- [ ] **Step 4: Write minimal implementation** — `apps/backend/archivum/capture/importers/chatgpt.py`

```python
"""Importer for ChatGPT data-export `conversations.json` (list of mappings)."""

from __future__ import annotations

import json
from pathlib import Path

from archivum.capture.importers import register
from archivum.capture.importers.base import ImportResult
from archivum.capture.redaction import HIDDEN_BLOCK_TYPES, redact_turn_text
from archivum.capture.schema import Conversation, Turn

_INTERFACE = "chatgpt_import"
_ROLES = {"user", "assistant", "system", "tool"}


class ChatGptImporter:
    interface = _INTERFACE

    def can_handle(self, path: Path) -> bool:
        if path.suffix != ".json":
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return isinstance(data, list) and all(
            isinstance(e, dict) and "mapping" in e for e in data
        )

    def parse(self, path: Path) -> ImportResult:
        data = json.loads(path.read_text(encoding="utf-8"))
        conversations: list[Conversation] = []
        for entry in data:
            title = str(entry.get("title", ""))
            create_time = entry.get("create_time", 0)
            nodes = [
                n["message"]
                for n in entry.get("mapping", {}).values()
                if isinstance(n, dict) and isinstance(n.get("message"), dict)
            ]
            turns: list[Turn] = []
            for msg in sorted(nodes, key=lambda m: m.get("create_time") or 0):
                content = msg.get("content") or {}
                if content.get("content_type") in HIDDEN_BLOCK_TYPES:
                    continue
                role = (msg.get("author") or {}).get("role", "user")
                if role not in _ROLES:
                    role = "user"
                text = redact_turn_text(
                    "\n".join(str(p) for p in content.get("parts", []) if p)
                )
                if not text:
                    continue
                ct = msg.get("create_time")
                turns.append(Turn(role=role, text=text, ts="" if ct is None else str(ct)))
            conversations.append(Conversation(
                session_id=f"{title}:{create_time}", interface=_INTERFACE,
                started_at=str(create_time), turns=tuple(turns), origin_uri=str(path),
            ))
        return ImportResult(conversations=tuple(conversations), interface=_INTERFACE)


register(ChatGptImporter())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_chatgpt_importer.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/capture/importers/chatgpt.py tests/fixtures/capture/chatgpt_export.json tests/capture/test_chatgpt_importer.py
git commit -m "feat(capture): ChatGPT export importer"
```

---

### Task 10: REST route — /api/sources/capture + /api/sources/capture/import

**Files:**
- Create: `apps/backend/archivum/api/capture.py`
- Modify: `apps/backend/archivum/main.py` (import + `app.include_router`)
- Test: `tests/capture/test_capture_api.py`

**Interfaces:**
- Consumes: `CaptureStore`/`CaptureResult` (Task 5); `Conversation`/`Turn`/`ToolCall` (Task 1); importer registry `connector_for` (Task 7); auth `require_writer`, `Settings`/`get_settings` (pattern: `archivum/api/sources.py`). Import the importer modules so they self-register.
- Produces: `router` (`APIRouter(prefix="/api/sources", tags=["capture"])`) with:
  - `POST /api/sources/capture` — body `CaptureConversationRequest(session_id, interface, turns: list[TurnModel], scope="personal", origin_uri="")` → `CaptureResponse`.
  - `POST /api/sources/capture/import` — body `CaptureImportRequest(path: str, scope="personal")` → `CaptureImportResponse(results: list[CaptureResponse])`. Dispatches via `connector_for`; 400 if no connector handles the path.

- [ ] **Step 1: Write the failing test** — `tests/capture/test_capture_api.py`

```python
import pytest
from starlette.testclient import TestClient

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings


@pytest.fixture
async def client(tmp_path, monkeypatch):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    monkeypatch.setattr("archivum.api.capture.get_settings", lambda: settings)

    from archivum.api.capture import router
    from archivum.auth import require_writer
    from fastapi import FastAPI

    app = FastAPI()
    app.dependency_overrides[require_writer] = lambda: {"username": "admin", "role": "owner"}
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=True)


def test_capture_endpoint_persists_conversation(client):
    resp = client.post("/api/sources/capture", json={
        "session_id": "s1", "interface": "claude_code_native",
        "turns": [
            {"role": "user", "text": "hi"},
            {"role": "assistant", "text": "<thinking>x</thinking> hello"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["deduplicated"] is False
    assert body["chunk_count"] == 2
    assert len(body["content_hash"]) == 64


def test_import_endpoint_rejects_unknown_file(client):
    resp = client.post("/api/sources/capture/import", json={"path": "/tmp/x.unknown"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_capture_api.py -q`
Expected: FAIL — `archivum.api.capture` missing.

- [ ] **Step 3: Write minimal implementation** — `apps/backend/archivum/api/capture.py`

```python
"""Capture routes: record AI sessions (native turns or imported files) as Sources."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from archivum.auth import CurrentUser, require_writer
from archivum.capture.importers import connector_for
from archivum.capture.importers import chatgpt as _chatgpt  # noqa: F401 (self-register)
from archivum.capture.importers import claude_code as _cc  # noqa: F401 (self-register)
from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.capture.store import CaptureResult, CaptureStore
from archivum.config import Settings, get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["capture"])


class ToolCallModel(BaseModel):
    name: str
    arguments: dict = {}
    result: str | None = None
    call_id: str | None = None
    ok: bool = True


class TurnModel(BaseModel):
    role: str
    text: str = ""
    ts: str = ""
    tool_calls: list[ToolCallModel] = []


class CaptureConversationRequest(BaseModel):
    session_id: str
    interface: str = "claude_code_native"
    started_at: str = ""
    turns: list[TurnModel] = []
    scope: str = "personal"
    origin_uri: str = ""


class CaptureImportRequest(BaseModel):
    path: str
    scope: str = "personal"


class CaptureResponse(BaseModel):
    source_id: str
    content_hash: str
    version: int
    document_id: str
    chunk_count: int
    deduplicated: bool


class CaptureImportResponse(BaseModel):
    interface: str
    results: list[CaptureResponse]


def _to_response(res: CaptureResult) -> CaptureResponse:
    return CaptureResponse(
        source_id=res.source_id, content_hash=res.content_hash, version=res.version,
        document_id=res.document_id, chunk_count=len(res.chunk_ids),
        deduplicated=res.deduplicated,
    )


def _build_conversation(body: CaptureConversationRequest) -> Conversation:
    turns = tuple(
        Turn(
            role=t.role, text=t.text, ts=t.ts,  # type: ignore[arg-type]
            tool_calls=tuple(
                ToolCall(name=c.name, arguments=c.arguments, result=c.result,
                         call_id=c.call_id, ok=c.ok)
                for c in t.tool_calls
            ),
        )
        for t in body.turns
    )
    return Conversation(
        session_id=body.session_id, interface=body.interface,
        started_at=body.started_at, turns=turns, scope=body.scope,
        origin_uri=body.origin_uri,
    )


@router.post("/capture", response_model=CaptureResponse)
async def capture_endpoint(
    body: CaptureConversationRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> CaptureResponse:
    store = CaptureStore(settings=settings)
    res = await store.capture(_build_conversation(body))
    return _to_response(res)


@router.post("/capture/import", response_model=CaptureImportResponse)
async def capture_import_endpoint(
    body: CaptureImportRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> CaptureImportResponse:
    path = Path(body.path)
    connector = connector_for(path)
    if connector is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"no importer for {body.path}", "code": "no_importer"},
        )
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"cannot read {body.path}", "code": "unreadable_source"},
        )
    store = CaptureStore(settings=settings)
    result = connector.parse(path)
    responses: list[CaptureResponse] = []
    for conv in result.conversations:
        scoped = conv if body.scope == "personal" else _rescope(conv, body.scope)
        responses.append(_to_response(await store.capture(scoped)))
    return CaptureImportResponse(interface=result.interface, results=responses)


def _rescope(conv: Conversation, scope: str) -> Conversation:
    import dataclasses

    return dataclasses.replace(conv, scope=scope)
```

Note: `CaptureStore(settings=settings)` builds its own `SourceStore()`/`BlobStore(settings.blob_dir)` — same as `archivum/api/sources.py` constructs `SourceStore()` per request. The test overrides `archivum.api.capture.get_settings` so the store's default settings point at the tmp DB/blobs.

- [ ] **Step 4: Mount the router** — edit `apps/backend/archivum/main.py`

Add with the other route imports (near line 25):

```python
from archivum.api.capture import router as capture_router
```

Add with the other `include_router` calls (near line 159, after `sources_router`):

```python
    app.include_router(capture_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run --project apps/backend pytest tests/capture/test_capture_api.py -q`
Expected: PASS (both tests).

- [ ] **Step 6: Guard test — router is mounted on the real app**

Append to `tests/capture/test_capture_api.py`:

```python
def test_capture_route_registered_on_app():
    from archivum.main import create_app

    paths = {r.path for r in create_app().routes}
    assert "/api/sources/capture" in paths
    assert "/api/sources/capture/import" in paths
```

Run: `uv run --project apps/backend pytest tests/capture/test_capture_api.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/archivum/api/capture.py apps/backend/archivum/main.py tests/capture/test_capture_api.py
git commit -m "feat(api): mount capture routes for native + imported AI sessions"
```

---

### Task 11: MCP tool — capture_conversation

**Files:**
- Modify: `apps/backend/archivum/mcp/server.py` (add impl + `@mcp.tool()` wrapper)
- Test: `tests/capture/test_mcp_capture.py`

**Interfaces:**
- Consumes: `CaptureStore` (Task 5); `Conversation`/`Turn` (Task 1). Mirrors the existing `@mcp.tool()` pattern (`ingest_source` at `server.py:54`).
- Produces: a testable core `capture_conversation_impl(*, session_id, interface, turns, scope="personal", origin_uri="") -> dict` returning `{"source_id","content_hash","version","chunks","deduplicated"}`, plus an `@mcp.tool()` wrapper `capture_conversation(...)` delegating to it. This is the agent-facing write path (spec §1: "MCP server for agent access (read and write)").

- [ ] **Step 1: Write the failing test** — `tests/capture/test_mcp_capture.py`

```python
import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings


@pytest.fixture
async def env(tmp_path, monkeypatch):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    monkeypatch.setattr("archivum.mcp.server.get_settings", lambda: settings)
    return settings


@pytest.mark.asyncio
async def test_capture_conversation_impl_persists_and_redacts(env):
    from archivum.mcp.server import capture_conversation_impl

    out = await capture_conversation_impl(
        session_id="s1", interface="claude_code_native",
        turns=[{"role": "user", "text": "hi"},
               {"role": "assistant", "text": "<thinking>x</thinking> hello"}],
    )
    assert out["deduplicated"] is False
    assert out["chunks"] == 2
    assert len(out["content_hash"]) == 64
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/capture/test_mcp_capture.py -q`
Expected: FAIL — `capture_conversation_impl` missing.

- [ ] **Step 3: Write minimal implementation** — append to `apps/backend/archivum/mcp/server.py`

Add imports near the other `archivum` imports (top of file):

```python
from archivum.capture.schema import Conversation, Turn
from archivum.capture.store import CaptureStore
```

Add near the other `@mcp.tool()` definitions:

```python
async def capture_conversation_impl(
    *,
    session_id: str,
    interface: str = "claude_code_native",
    turns: list[dict[str, Any]],
    scope: str = "personal",
    origin_uri: str = "",
) -> dict[str, Any]:
    """Core (testable) capture path: build a Conversation and persist it."""
    conv = Conversation(
        session_id=session_id, interface=interface, started_at="",
        turns=tuple(
            Turn(role=t.get("role", "user"), text=t.get("text", ""),  # type: ignore[arg-type]
                 ts=t.get("ts", ""))
            for t in turns
        ),
        scope=scope, origin_uri=origin_uri,
    )
    store = CaptureStore(settings=get_settings())
    res = await store.capture(conv)
    return {
        "source_id": res.source_id,
        "content_hash": res.content_hash,
        "version": res.version,
        "chunks": len(res.chunk_ids),
        "deduplicated": res.deduplicated,
    }


@mcp.tool()
async def capture_conversation(
    session_id: str,
    interface: str = "claude_code_native",
    turns: list[dict[str, Any]] | None = None,
    scope: str = "personal",
) -> dict[str, Any]:
    """Capture a user-visible AI conversation as an immutable Source.

    `turns` is a list of {"role","text","ts?"} dicts. Hidden reasoning is stripped.
    """
    _require_key()
    set_trace_id(new_trace_id("mcp-capture"))
    return await capture_conversation_impl(
        session_id=session_id, interface=interface, turns=turns or [], scope=scope,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/capture/test_mcp_capture.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/mcp/server.py tests/capture/test_mcp_capture.py
git commit -m "feat(capture): MCP capture_conversation tool"
```

---

### Task 12: Integration — idempotent re-import + no-hidden-reasoning across all sources

**Files:**
- Test: `tests/capture/test_integration.py`

**Interfaces:** none new. Proves (a) parse→capture twice for a file yields zero duplicate sources/documents/chunks, and (b) no hidden marker from any capture path reaches L1 `documents`/`chunks`/blobs.

- [ ] **Step 1: Write the test** — `tests/capture/test_integration.py`

```python
from pathlib import Path

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.capture.importers.chatgpt import ChatGptImporter
from archivum.capture.importers.claude_code import ClaudeCodeImporter
from archivum.capture.native import NativeCaptureWriter
from archivum.capture.store import CaptureStore
from archivum.config import Settings
from archivum.db.sqlite import get_db
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore

FIXDIR = Path(__file__).parent.parent / "fixtures" / "capture"
SECRETS = ("internal plan", "hidden reasoning", "secret chain")


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    store = CaptureStore(store=SourceStore(), blob_store=BlobStore(settings.blob_dir),
                         settings=settings)
    return settings, store


async def _counts():
    async with get_db() as db:
        out = {}
        for t in ("sources", "documents", "chunks"):
            async with db.execute(f"SELECT COUNT(*) AS n FROM {t}") as cur:
                out[t] = (await cur.fetchone())["n"]
        return out


@pytest.mark.asyncio
async def test_reimport_is_a_noop(env):
    _, store = env
    conv = ClaudeCodeImporter().parse(FIXDIR / "claude_code_session.jsonl").conversations[0]
    await store.capture(conv)
    first = await _counts()
    again = ClaudeCodeImporter().parse(FIXDIR / "claude_code_session.jsonl").conversations[0]
    await store.capture(again)
    assert await _counts() == first


@pytest.mark.asyncio
async def test_no_hidden_reasoning_from_any_source(env):
    settings, store = env
    await store.capture(ClaudeCodeImporter().parse(FIXDIR / "claude_code_session.jsonl").conversations[0])
    await store.capture(ChatGptImporter().parse(FIXDIR / "chatgpt_export.json").conversations[0])
    w = NativeCaptureWriter(store, session_id="native1")
    w.record_turn("assistant", "<thinking>secret chain</thinking> ok")
    await w.flush()

    async with get_db() as db:
        async with db.execute("SELECT normalized_hash FROM documents") as cur:
            _ = await cur.fetchall()
    # L0 blobs hold canonical JSON — verify no secret survived into any blob.
    blobs = BlobStore(settings.blob_dir)
    async with get_db() as db:
        async with db.execute("SELECT content_hash FROM sources") as cur:
            hashes = [r["content_hash"] for r in await cur.fetchall()]
    corpus = " ".join(blobs.get(h).decode("utf-8") for h in hashes)
    for secret in SECRETS:
        assert secret not in corpus
```

- [ ] **Step 2: Run the full capture suite**

Run: `uv run --project apps/backend pytest tests/capture -q`
Expected: ALL PASS.

- [ ] **Step 3: Run the whole backend suite (no regressions in PER-315)**

Run: `uv run --project apps/backend pytest -q`
Expected: ALL PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/capture/test_integration.py
git commit -m "test(capture): idempotent re-import + no-hidden-reasoning across all sources"
```

---

## Self-Review

**1. Spec coverage.**
- §1 no-hidden-reasoning → Tasks 2, 6, 8, 9, 12. §1 MCP write path → Task 11. §1 REST → Task 10.
- §2 L0 content-address + versioned → Tasks 3, 5 (blob `put`, per-origin version via `SourceStore.latest_version_for_origin`).
- §4 lineage `Source→Document→Chunk` → Task 5 (one chunk per turn, Task 4 spans).
- §5 "each agent session captured as a Source", semantic-cache/idempotent → Tasks 5, 6, 12.
- §6.1 immutability (new version, never overwrite) → delegated to PER-315 primitives, asserted in Task 5 `test_changed_content_creates_v2_without_mutating_v1`.
- PER-316 issue coverage: conversations (schema T1, store T5), tool activity (T4 transcript + T8 tool_use/tool_result folding), decisions/outcomes (schema + native writer T6, preserved in canonical evidence), task outcomes (T6), native capture (T6), imports + connectors (T7) with two importers (T8, T9).
- **Deliberate scope boundary:** knowledge-object rows (Event/Claim/Entity/Relationship) are OUT — PER-317. Decisions/outcomes/tool-calls are preserved inside the L0 evidence + rendered transcript so PER-317 extracts them with full provenance. Confirmed with the user 2026-07-28.

**2. Placeholder scan.** No `TODO`/`...`/`pass`-only shipped bodies. Every function in an Interfaces block has a task that implements it with full code. Fixtures are concrete literal files. `_require_key`, `set_trace_id`, `new_trace_id`, `get_settings` referenced in Task 11 already exist in `server.py`.

**3. Type consistency.** `Conversation`/`Turn`/`ToolCall`/`Decision`/`Outcome`/`Role` defined once (T1), imported everywhere. `CaptureResult`/`CaptureStore` (T5), `ImportResult`/`ImportConnector` (T7) defined once. IDs are `str` throughout (matches PER-315 `new_id()`), chunk fields are `start_offset`/`end_offset` and `text_hash` (matches `store.models.Chunk` and `store.schema`). `render_transcript` returns `(str, list[TurnSpan])` and is consumed only in T5. No new tables — all writes go through `SourceStore`/`BlobStore` against the existing `EVIDENCE_SCHEMA`.

**Correction vs the prior draft of this plan (2026-07-28):** the earlier version predated PER-315's implementation and assumed `archivum/ingest/source_store.py::SourceStore.put(...)->StoredSource` with integer ids, a `capture_sql.py` with `INTEGER AUTOINCREMENT` tables, `span_start/span_end` columns, an `_SqliteSourceStore` adapter, `events`/`claims` tables, and a `conftest.py` with `Settings(wiki_dir=,raw_dir=,db_path=,kuzu_path=)`. All were wrong against the real code (`store/repository.py` TEXT-id `SourceStore`, `store/blobs.py` `BlobStore`, `store/schema.py` `EVIDENCE_SCHEMA`, `Settings.blob_dir`, root `pytest.ini`). This plan reuses the real primitives, adds no tables, and defers knowledge objects to PER-317.
