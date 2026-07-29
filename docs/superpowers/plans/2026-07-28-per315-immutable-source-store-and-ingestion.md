# PER-315: Immutable Source Store & Universal Ingestion — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the content-addressed, versioned L0 evidence blob store plus the L1 `Source`/`Document`/`Chunk` tables and the deterministic ingestion stage (parse → normalize → chunk), exposing a reusable `SourceStore` API and an `ingest_source()` entrypoint that later epics (317/318/319) consume.

**Architecture:** L0 is a write-once blob store on disk keyed by `sha256(bytes)` — evidence is immutable and never overwritten by generated knowledge. L1 lives in the existing SQLite database (`archivum.db`) via `aiosqlite`, holding `sources`, `documents`, and `chunks` rows that reference blobs by hash and carry bitemporal + provenance metadata. The deterministic ingestion stage re-uses the existing `archivum.ingest.parsers` to normalize bytes into a `Document`, chunks the normalized text with stable span anchors, and records everything transactionally; re-ingesting a changed source creates a **new version**, never mutating the old.

**Tech Stack:** Python 3.12+, FastAPI (async), `aiosqlite`, existing `archivum.ingest.parsers`, `hashlib` (stdlib sha256), `pytest` + `pytest-asyncio` (`asyncio_mode=auto`), `uv` for dependency/run management. No new third-party dependencies.

## Global Constraints

- **SQLite is canonical for L1** — the single `archivum.db` file is the store of record; back it up as precious data. (spec §2, §3)
- **L0 is immutable & content-addressed** — every blob is keyed by `sha256` of its raw bytes and written exactly once; generated knowledge can NEVER overwrite evidence. (spec §2 L0, §6.1)
- **Versioned, never mutated** — re-ingesting a changed source creates a new `version`, never mutating the old row or blob. (spec §2 L0)
- **Indexes are rebuildable** — nothing in L2 (Qdrant/Kuzu/FTS) is a source of truth; L0+L1 alone must be sufficient to rebuild everything. Do not put canonical data only in an index. (spec §2 L2, §6.6)
- **Provenance invariants** — every L1 `Chunk` carries a `text_hash` and a stable span; every knowledge object (future epics) will cite ≥1 chunk. `extraction_method ∈ {EXTRACTED, INFERRED, AMBIGUOUS}`. (spec §4, §6.2, §6.3)
- **Bitemporal + scope metadata** — objects carry `valid_from` / `valid_to` (world time), `recorded_at` (learn time), and a `scope` partition/access label. (spec §4)
- **Python 3.12+** — `requires-python = ">=3.12"`. (`pyproject.toml`)
- **Evolve in place** — keep the existing stack (FastAPI, SQLite, `aiosqlite`, `uv`, pytest). Add the blob store; reshape SQLite additively. Do not rewrite existing modules. (spec §3, §9)

---

## File Structure

| File | Responsibility |
|------|----------------|
| `apps/backend/archivum/store/__init__.py` | Package marker for the L0/L1 source-store package. |
| `apps/backend/archivum/store/hashing.py` | Pure sha256 helpers: `sha256_bytes`, `sha256_text`. Single source of the content-address function. |
| `apps/backend/archivum/store/blobs.py` | L0 blob store: write-once, content-addressed disk storage (`BlobStore` class). |
| `apps/backend/archivum/store/schema.py` | SQL DDL string for `sources`, `documents`, `chunks` (L1 evidence lineage). Applied idempotently. |
| `apps/backend/archivum/store/source_types.py` | The `SourceType` enum + registry mapping raw inputs to a source type. |
| `apps/backend/archivum/store/models.py` | Frozen dataclasses: `Source`, `Document`, `Chunk`, `IngestResult`, `ExtractionMethod`. |
| `apps/backend/archivum/store/repository.py` | `SourceStore` — async CRUD over L1 tables (insert source/document/chunk, version lookup, dedup lookup, read-back). |
| `apps/backend/archivum/store/chunking.py` | Deterministic text chunker producing `ChunkSpec` with stable offset spans. |
| `apps/backend/archivum/store/normalize.py` | Adapts existing `archivum.ingest.parsers.parse_source` bytes → normalized `Document` text + mime. |
| `apps/backend/archivum/store/ingest.py` | `ingest_source()` orchestration: content-address → dedup/version → parse → chunk → persist, transactionally. |
| `apps/backend/archivum/api/sources.py` | FastAPI router `/api/sources/*`: ingest endpoint + read-back endpoints. |
| `apps/backend/archivum/db/sqlite.py:17-225` | Modify: apply the L0/L1 evidence schema at `init_db` time (import + executescript). |
| `apps/backend/archivum/config.py:32-36` | Modify: add `blob_dir` data path setting. |
| `apps/backend/archivum/main.py` | Modify: register the sources router and configure the blob store on startup. |
| `tests/store/test_hashing.py` | Tests for hashing helpers. |
| `tests/store/test_blobs.py` | Tests for write-once/dedup/immutability of the blob store. |
| `tests/store/test_source_types.py` | Tests for source-type detection. |
| `tests/store/test_chunking.py` | Tests for deterministic chunk spans. |
| `tests/store/test_normalize.py` | Tests for parser adaptation → Document. |
| `tests/store/test_repository.py` | Tests for `SourceStore` CRUD, dedup, versioning (mocked `get_db`). |
| `tests/store/test_ingest.py` | Tests for `ingest_source()` orchestration + invariants (dedup, re-ingest = new version, immutability). |
| `tests/api/test_sources.py` | Tests for the `/api/sources` endpoints. |

---

## Task 1: sha256 hashing helpers

**Files:**
- Create: `apps/backend/archivum/store/__init__.py`
- Create: `apps/backend/archivum/store/hashing.py`
- Test: `tests/store/test_hashing.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `sha256_bytes(data: bytes) -> str` — hex digest (64 lowercase hex chars).
  - `sha256_text(text: str, *, encoding: str = "utf-8") -> str` — hex digest of `text.encode(encoding)`.

- [ ] **Step 1: Create the package marker**

Create `apps/backend/archivum/store/__init__.py` with a single line:

```python
"""L0 immutable evidence store + L1 evidence-lineage repository."""
```

- [ ] **Step 2: Write the failing test**

Create `tests/store/test_hashing.py`:

```python
"""Tests for archivum.store.hashing."""

from __future__ import annotations

import hashlib

from archivum.store.hashing import sha256_bytes, sha256_text


def test_sha256_bytes_matches_hashlib():
    data = b"hello archivum"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_sha256_bytes_is_64_hex_chars():
    digest = sha256_bytes(b"anything")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_sha256_text_equals_bytes_of_utf8():
    assert sha256_text("café") == sha256_bytes("café".encode("utf-8"))


def test_sha256_is_deterministic():
    assert sha256_bytes(b"x") == sha256_bytes(b"x")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_hashing.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.hashing'`

- [ ] **Step 4: Write minimal implementation**

Create `apps/backend/archivum/store/hashing.py`:

```python
"""Content-addressing primitives — sha256 over raw bytes."""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex sha256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str, *, encoding: str = "utf-8") -> str:
    """Return the sha256 digest of text encoded with `encoding` (default utf-8)."""
    return sha256_bytes(text.encode(encoding))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_hashing.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/store/__init__.py apps/backend/archivum/store/hashing.py tests/store/test_hashing.py
git commit -m "feat(store): add sha256 content-addressing helpers"
```

---

## Task 2: L0 write-once content-addressed blob store

**Files:**
- Create: `apps/backend/archivum/store/blobs.py`
- Test: `tests/store/test_blobs.py`

**Interfaces:**
- Consumes: `sha256_bytes` from Task 1.
- Produces:
  - `class BlobStore` with:
    - `__init__(self, root: Path)` — stores blobs under `root`.
    - `put(self, data: bytes) -> str` — writes bytes once, returns `content_hash` (hex). Idempotent: writing identical bytes returns the same hash and does NOT rewrite an existing blob.
    - `get(self, content_hash: str) -> bytes` — reads bytes back; raises `KeyError` if absent.
    - `exists(self, content_hash: str) -> bool`.
    - `path_for(self, content_hash: str) -> Path` — sharded path (`root/ab/cd/<hash>`).
  - `class BlobImmutabilityError(RuntimeError)` — raised on any attempt to overwrite an existing blob with different bytes.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_blobs.py`:

```python
"""Tests for the L0 content-addressed blob store."""

from __future__ import annotations

import pytest

from archivum.store.blobs import BlobImmutabilityError, BlobStore
from archivum.store.hashing import sha256_bytes


def test_put_returns_content_hash(tmp_path):
    store = BlobStore(tmp_path)
    data = b"evidence bytes"
    h = store.put(data)
    assert h == sha256_bytes(data)


def test_get_roundtrips(tmp_path):
    store = BlobStore(tmp_path)
    data = b"round trip"
    h = store.put(data)
    assert store.get(h) == data


def test_put_is_deduplicated_and_write_once(tmp_path):
    store = BlobStore(tmp_path)
    data = b"same bytes"
    h1 = store.put(data)
    mtime_before = store.path_for(h1).stat().st_mtime_ns
    h2 = store.put(data)
    mtime_after = store.path_for(h1).stat().st_mtime_ns
    assert h1 == h2
    # Second put must NOT rewrite the existing blob.
    assert mtime_before == mtime_after


def test_exists(tmp_path):
    store = BlobStore(tmp_path)
    h = store.put(b"x")
    assert store.exists(h) is True
    assert store.exists("0" * 64) is False


def test_get_missing_raises_keyerror(tmp_path):
    store = BlobStore(tmp_path)
    with pytest.raises(KeyError):
        store.get("0" * 64)


def test_corrupted_blob_with_wrong_bytes_is_rejected(tmp_path):
    store = BlobStore(tmp_path)
    h = store.put(b"correct")
    # Simulate a pre-existing file at the target path with different bytes.
    path = store.path_for(h)
    path.write_bytes(b"tampered")
    with pytest.raises(BlobImmutabilityError):
        store.put(b"correct")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_blobs.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.blobs'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/blobs.py`:

```python
"""L0 immutable evidence: content-addressed, write-once blob store on disk."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from archivum.store.hashing import sha256_bytes


class BlobImmutabilityError(RuntimeError):
    """Raised when an existing blob's bytes do not match the content hash."""


class BlobStore:
    """Write-once content-addressed store. Blobs are keyed by sha256(bytes)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, content_hash: str) -> Path:
        """Sharded path: root/<h[0:2]>/<h[2:4]>/<hash> to avoid huge dirs."""
        return self.root / content_hash[0:2] / content_hash[2:4] / content_hash

    def exists(self, content_hash: str) -> bool:
        return self.path_for(content_hash).is_file()

    def put(self, data: bytes) -> str:
        """Write `data` once and return its content hash. Idempotent."""
        content_hash = sha256_bytes(data)
        target = self.path_for(content_hash)
        if target.exists():
            # Write-once: verify the existing blob matches; never overwrite.
            if target.read_bytes() != data:
                raise BlobImmutabilityError(
                    f"blob {content_hash} exists with different bytes"
                )
            return content_hash

        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to a temp file in the same dir, then rename.
        fd, tmp_name = tempfile.mkstemp(dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return content_hash

    def get(self, content_hash: str) -> bytes:
        target = self.path_for(content_hash)
        if not target.is_file():
            raise KeyError(content_hash)
        return target.read_bytes()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_blobs.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/blobs.py tests/store/test_blobs.py
git commit -m "feat(store): add L0 write-once content-addressed blob store"
```

---

## Task 3: source-type registry

**Files:**
- Create: `apps/backend/archivum/store/source_types.py`
- Test: `tests/store/test_source_types.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `class SourceType(str, Enum)` with members: `DOCUMENT`, `WEB_PAGE`, `CONVERSATION`, `REPOSITORY`, `MESSAGE`, `MEDIA`, `TEST_RUN`, `DEPLOYMENT`.
  - `detect_source_type(*, origin_uri: str, mime: str | None = None, explicit: SourceType | str | None = None) -> SourceType` — resolves a source type from an explicit hint, else the origin URI/mime.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_source_types.py`:

```python
"""Tests for the source-type registry."""

from __future__ import annotations

import pytest

from archivum.store.source_types import SourceType, detect_source_type


def test_explicit_enum_wins():
    assert (
        detect_source_type(origin_uri="whatever", explicit=SourceType.DEPLOYMENT)
        == SourceType.DEPLOYMENT
    )


def test_explicit_string_is_coerced():
    assert (
        detect_source_type(origin_uri="whatever", explicit="repository")
        == SourceType.REPOSITORY
    )


def test_http_url_is_web_page():
    assert detect_source_type(origin_uri="https://example.com/x") == SourceType.WEB_PAGE


def test_git_uri_is_repository():
    assert detect_source_type(origin_uri="git@github.com:me/repo.git") == SourceType.REPOSITORY


def test_media_by_mime():
    assert detect_source_type(origin_uri="file:///a.mp4", mime="video/mp4") == SourceType.MEDIA


def test_message_by_mime():
    assert detect_source_type(origin_uri="file:///a.eml", mime="message/rfc822") == SourceType.MESSAGE


def test_default_is_document():
    assert detect_source_type(origin_uri="file:///notes.txt", mime="text/plain") == SourceType.DOCUMENT


def test_invalid_explicit_raises():
    with pytest.raises(ValueError):
        detect_source_type(origin_uri="x", explicit="not-a-type")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_source_types.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.source_types'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/source_types.py`:

```python
"""Source-type registry: the closed set of ingestible source kinds (spec §4)."""

from __future__ import annotations

from enum import Enum


class SourceType(str, Enum):
    DOCUMENT = "document"
    WEB_PAGE = "web_page"
    CONVERSATION = "conversation"
    REPOSITORY = "repository"
    MESSAGE = "message"
    MEDIA = "media"
    TEST_RUN = "test_run"
    DEPLOYMENT = "deployment"


_MEDIA_MIME_PREFIXES = ("audio/", "video/", "image/")
_MESSAGE_MIMES = frozenset({"message/rfc822", "application/mbox"})


def detect_source_type(
    *,
    origin_uri: str,
    mime: str | None = None,
    explicit: SourceType | str | None = None,
) -> SourceType:
    """Resolve a SourceType from an explicit hint, else origin URI / mime."""
    if explicit is not None:
        return SourceType(explicit)  # raises ValueError on bad string

    uri = origin_uri.lower()
    if uri.startswith("git@") or uri.endswith(".git"):
        return SourceType.REPOSITORY
    if uri.startswith(("http://", "https://")):
        return SourceType.WEB_PAGE

    if mime:
        m = mime.lower()
        if m in _MESSAGE_MIMES:
            return SourceType.MESSAGE
        if m.startswith(_MEDIA_MIME_PREFIXES):
            return SourceType.MEDIA

    return SourceType.DOCUMENT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_source_types.py -v`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/source_types.py tests/store/test_source_types.py
git commit -m "feat(store): add source-type registry and detection"
```

---

## Task 4: L1 evidence-lineage models

**Files:**
- Create: `apps/backend/archivum/store/models.py`
- Test: `tests/store/test_models.py`

**Interfaces:**
- Consumes: `SourceType` from Task 3.
- Produces (all frozen dataclasses; `id` fields are text UUID hex strings):
  - `class ExtractionMethod(str, Enum)` — `EXTRACTED`, `INFERRED`, `AMBIGUOUS`.
  - `Source(id, content_hash, version, source_type, origin_uri, scope, ingested_at, recorded_at, valid_from, valid_to)` — `version: int`, `source_type: SourceType`, `valid_to: str | None`.
  - `Document(id, source_id, mime, normalized_hash)`.
  - `Chunk(id, document_id, seq, start_offset, end_offset, text_hash)` — `seq: int`, offsets `int`.
  - `IngestResult(source, document, chunks, deduplicated)` — `chunks: list[Chunk]`, `deduplicated: bool`.
  - `new_id() -> str` — returns `uuid.uuid4().hex`.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_models.py`:

```python
"""Tests for L1 evidence-lineage models."""

from __future__ import annotations

import dataclasses

from archivum.store.models import (
    Chunk,
    Document,
    ExtractionMethod,
    IngestResult,
    Source,
    new_id,
)
from archivum.store.source_types import SourceType


def test_new_id_is_32_hex():
    i = new_id()
    assert len(i) == 32
    assert all(c in "0123456789abcdef" for c in i)


def test_new_id_is_unique():
    assert new_id() != new_id()


def test_extraction_method_values():
    assert {m.value for m in ExtractionMethod} == {"EXTRACTED", "INFERRED", "AMBIGUOUS"}


def test_source_is_frozen():
    s = Source(
        id="a" * 32,
        content_hash="b" * 64,
        version=1,
        source_type=SourceType.DOCUMENT,
        origin_uri="file:///x.txt",
        scope="personal",
        ingested_at="2026-07-28T00:00:00+00:00",
        recorded_at="2026-07-28T00:00:00+00:00",
        valid_from="2026-07-28T00:00:00+00:00",
        valid_to=None,
    )
    assert s.version == 1
    try:
        s.version = 2  # type: ignore[misc]
        raise AssertionError("Source must be frozen")
    except dataclasses.FrozenInstanceError:
        pass


def test_ingest_result_carries_chunks():
    src = Source(
        id="a" * 32, content_hash="b" * 64, version=1,
        source_type=SourceType.DOCUMENT, origin_uri="file:///x", scope="personal",
        ingested_at="t", recorded_at="t", valid_from="t", valid_to=None,
    )
    doc = Document(id="c" * 32, source_id=src.id, mime="text/plain", normalized_hash="d" * 64)
    chunk = Chunk(id="e" * 32, document_id=doc.id, seq=0, start_offset=0, end_offset=5, text_hash="f" * 64)
    result = IngestResult(source=src, document=doc, chunks=[chunk], deduplicated=False)
    assert result.chunks[0].end_offset == 5
    assert result.deduplicated is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.models'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/models.py`:

```python
"""L1 evidence-lineage models: Source → Document → Chunk (spec §4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from archivum.store.source_types import SourceType


def new_id() -> str:
    """Stable opaque id for L1 objects."""
    return uuid.uuid4().hex


class ExtractionMethod(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    content_hash: str
    version: int
    source_type: SourceType
    origin_uri: str
    scope: str
    ingested_at: str
    recorded_at: str
    valid_from: str
    valid_to: str | None


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    source_id: str
    mime: str
    normalized_hash: str


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    document_id: str
    seq: int
    start_offset: int
    end_offset: int
    text_hash: str


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: Source
    document: Document
    chunks: list[Chunk]
    deduplicated: bool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_models.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/models.py tests/store/test_models.py
git commit -m "feat(store): add L1 evidence-lineage dataclasses"
```

---

## Task 5: L1 SQL schema

**Files:**
- Create: `apps/backend/archivum/store/schema.py`
- Test: `tests/store/test_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `EVIDENCE_SCHEMA: str` — DDL creating `sources`, `documents`, `chunks` with `CREATE TABLE IF NOT EXISTS`.
  - Columns (exact):
    - `sources(id TEXT PK, content_hash TEXT, version INTEGER, source_type TEXT, origin_uri TEXT, scope TEXT, ingested_at TEXT, recorded_at TEXT, valid_from TEXT, valid_to TEXT NULL, UNIQUE(content_hash, version))`.
    - `documents(id TEXT PK, source_id TEXT FK→sources, mime TEXT, normalized_hash TEXT)`.
    - `chunks(id TEXT PK, document_id TEXT FK→documents, seq INTEGER, start_offset INTEGER, end_offset INTEGER, text_hash TEXT, UNIQUE(document_id, seq))`.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_schema.py`:

```python
"""Tests that the evidence schema is valid, idempotent SQLite DDL."""

from __future__ import annotations

import sqlite3

from archivum.store.schema import EVIDENCE_SCHEMA


def _apply(conn):
    conn.executescript(EVIDENCE_SCHEMA)


def test_schema_applies_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    _apply(conn)  # second run must not error (IF NOT EXISTS)
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"sources", "documents", "chunks"} <= tables


def test_sources_unique_content_hash_version():
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    row = (
        "id1", "h" * 64, 1, "document", "file:///x", "personal",
        "t", "t", "t", None,
    )
    cols = "id, content_hash, version, source_type, origin_uri, scope, ingested_at, recorded_at, valid_from, valid_to"
    conn.execute(f"INSERT INTO sources ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?)", row)
    dup = ("id2", "h" * 64, 1, "document", "file:///x", "personal", "t", "t", "t", None)
    try:
        conn.execute(f"INSERT INTO sources ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?)", dup)
        raise AssertionError("duplicate (content_hash, version) must be rejected")
    except sqlite3.IntegrityError:
        pass


def test_chunks_unique_document_seq():
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    conn.execute(
        "INSERT INTO chunks (id, document_id, seq, start_offset, end_offset, text_hash) "
        "VALUES (?,?,?,?,?,?)",
        ("c1", "d1", 0, 0, 5, "t" * 64),
    )
    try:
        conn.execute(
            "INSERT INTO chunks (id, document_id, seq, start_offset, end_offset, text_hash) "
            "VALUES (?,?,?,?,?,?)",
            ("c2", "d1", 0, 0, 5, "t" * 64),
        )
        raise AssertionError("duplicate (document_id, seq) must be rejected")
    except sqlite3.IntegrityError:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_schema.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.schema'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/schema.py`:

```python
"""L1 evidence-lineage SQLite schema (spec §4). Applied idempotently at init."""

from __future__ import annotations

EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            TEXT    PRIMARY KEY,
    content_hash  TEXT    NOT NULL,
    version       INTEGER NOT NULL,
    source_type   TEXT    NOT NULL,
    origin_uri    TEXT    NOT NULL,
    scope         TEXT    NOT NULL DEFAULT 'personal',
    ingested_at   TEXT    NOT NULL,
    recorded_at   TEXT    NOT NULL,
    valid_from    TEXT    NOT NULL,
    valid_to      TEXT,
    UNIQUE(content_hash, version)
);

CREATE INDEX IF NOT EXISTS idx_sources_content_hash ON sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_sources_origin_uri ON sources(origin_uri);
CREATE INDEX IF NOT EXISTS idx_sources_scope ON sources(scope);

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    mime            TEXT NOT NULL,
    normalized_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);

CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT    PRIMARY KEY,
    document_id  TEXT    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset   INTEGER NOT NULL,
    text_hash    TEXT    NOT NULL,
    UNIQUE(document_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks(text_hash);
"""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_schema.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/schema.py tests/store/test_schema.py
git commit -m "feat(store): add L1 sources/documents/chunks schema"
```

---

## Task 6: apply the evidence schema at init_db

**Files:**
- Modify: `apps/backend/archivum/db/sqlite.py:249-255` (the `init_db` function) and the imports block near `apps/backend/archivum/db/sqlite.py:1-13`.
- Test: `tests/store/test_schema_init.py`

**Interfaces:**
- Consumes: `EVIDENCE_SCHEMA` from Task 5; existing `init_db(settings)` and `get_db()`.
- Produces: after `init_db`, tables `sources`, `documents`, `chunks` exist in the configured DB.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_schema_init.py`:

```python
"""init_db must also create the L0/L1 evidence tables."""

from __future__ import annotations

import aiosqlite
import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings


@pytest.mark.asyncio
async def test_init_db_creates_evidence_tables(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db")
    await sqlite_mod.init_db(settings)
    async with aiosqlite.connect(str(settings.db_path)) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            names = {r[0] for r in await cur.fetchall()}
    assert {"sources", "documents", "chunks"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_schema_init.py -v`
Expected: FAIL — assertion error (evidence tables missing).

- [ ] **Step 3: Add the import**

In `apps/backend/archivum/db/sqlite.py`, after the existing `from archivum.config import Settings, get_settings` line (near line 13), add:

```python
from archivum.store.schema import EVIDENCE_SCHEMA
```

- [ ] **Step 4: Apply the schema in init_db**

Modify the `init_db` function body (currently lines 251-255) so both schema strings are applied:

```python
async def init_db(settings: Settings) -> None:
    configure(settings)
    async with get_db() as db:
        await db.executescript(_SCHEMA)
        await db.executescript(EVIDENCE_SCHEMA)
        await db.commit()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_schema_init.py -v`
Expected: PASS (1 passed)

- [ ] **Step 6: Commit**

```bash
git add apps/backend/archivum/db/sqlite.py tests/store/test_schema_init.py
git commit -m "feat(store): apply evidence schema during init_db"
```

---

## Task 7: deterministic chunker with stable span anchors

**Files:**
- Create: `apps/backend/archivum/store/chunking.py`
- Test: `tests/store/test_chunking.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `@dataclass(frozen=True) class ChunkSpec(seq: int, start_offset: int, end_offset: int, text: str)`.
  - `chunk_text(text: str, *, target_chars: int = 1200, overlap_chars: int = 100) -> list[ChunkSpec]` — splits on paragraph boundaries where possible, deterministic, `end_offset` exclusive, `text == source_text[start_offset:end_offset]`. Empty/whitespace-only input returns `[]`.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_chunking.py`:

```python
"""Tests for the deterministic span-anchored chunker."""

from __future__ import annotations

from archivum.store.chunking import ChunkSpec, chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []


def test_short_text_is_one_chunk():
    text = "Hello world."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].seq == 0
    assert chunks[0].text == text
    assert chunks[0].start_offset == 0
    assert chunks[0].end_offset == len(text)


def test_spans_are_exact_slices_of_source():
    text = "\n\n".join(f"Paragraph number {i} " * 40 for i in range(6))
    chunks = chunk_text(text, target_chars=300, overlap_chars=0)
    assert len(chunks) > 1
    for c in chunks:
        assert text[c.start_offset:c.end_offset] == c.text


def test_seq_is_monotonic_from_zero():
    text = "\n\n".join(f"Block {i} " * 40 for i in range(5))
    chunks = chunk_text(text, target_chars=200, overlap_chars=0)
    assert [c.seq for c in chunks] == list(range(len(chunks)))


def test_is_deterministic():
    text = "\n\n".join(f"Para {i} " * 30 for i in range(4))
    assert chunk_text(text, target_chars=250) == chunk_text(text, target_chars=250)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.chunking'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/chunking.py`:

```python
"""Deterministic text chunker producing stable offset-anchored spans."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChunkSpec:
    seq: int
    start_offset: int
    end_offset: int
    text: str


def chunk_text(
    text: str,
    *,
    target_chars: int = 1200,
    overlap_chars: int = 100,
) -> list[ChunkSpec]:
    """Split `text` into overlapping spans on paragraph boundaries.

    Deterministic: identical input + params always yields identical spans.
    `text[start_offset:end_offset]` equals each chunk's `text`.
    """
    if not text.strip():
        return []

    n = len(text)
    if n <= target_chars:
        return [ChunkSpec(seq=0, start_offset=0, end_offset=n, text=text)]

    specs: list[ChunkSpec] = []
    seq = 0
    start = 0
    while start < n:
        end = min(start + target_chars, n)
        if end < n:
            # Prefer to break on the last paragraph boundary within the window.
            boundary = text.rfind("\n\n", start, end)
            if boundary > start:
                end = boundary
            else:
                space = text.rfind(" ", start, end)
                if space > start:
                    end = space
        specs.append(
            ChunkSpec(seq=seq, start_offset=start, end_offset=end, text=text[start:end])
        )
        seq += 1
        if end >= n:
            break
        start = max(end - overlap_chars, start + 1)
    return specs
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_chunking.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/chunking.py tests/store/test_chunking.py
git commit -m "feat(store): add deterministic span-anchored chunker"
```

---

## Task 8: normalization adapter over existing parsers

**Files:**
- Create: `apps/backend/archivum/store/normalize.py`
- Test: `tests/store/test_normalize.py`

**Interfaces:**
- Consumes: existing `archivum.ingest.parsers.parse_source` (returns `ParsedDoc(text, metadata, source)`).
- Produces:
  - `@dataclass(frozen=True) class NormalizedDoc(text: str, mime: str, metadata: dict[str, Any])`.
  - `async def normalize(origin_uri: str) -> NormalizedDoc` — dispatches to `parse_source`, maps its `metadata["type"]` to a mime string via `_TYPE_TO_MIME`, returns normalized text + mime.
  - `_TYPE_TO_MIME: dict[str, str]` — at minimum maps `"md"→"text/markdown"`, `"txt"→"text/plain"`, `"pdf"→"application/pdf"`, `"html"→"text/html"`, `"url"→"text/html"`, `"code"→"text/x-code"`, and falls back to `"text/plain"`.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_normalize.py`:

```python
"""Tests for the normalization adapter over archivum.ingest.parsers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from archivum.ingest.parsers import ParsedDoc
from archivum.store.normalize import NormalizedDoc, normalize


@pytest.mark.asyncio
async def test_normalize_maps_markdown_mime(tmp_path):
    parsed = ParsedDoc(text="# Title\n\nBody", metadata={"type": "md"}, source="x.md")
    with patch(
        "archivum.store.normalize.parse_source",
        new=AsyncMock(return_value=parsed),
    ):
        result = await normalize("file:///x.md")
    assert isinstance(result, NormalizedDoc)
    assert result.text == "# Title\n\nBody"
    assert result.mime == "text/markdown"


@pytest.mark.asyncio
async def test_normalize_unknown_type_falls_back_to_plain():
    parsed = ParsedDoc(text="data", metadata={"type": "weird"}, source="x")
    with patch(
        "archivum.store.normalize.parse_source",
        new=AsyncMock(return_value=parsed),
    ):
        result = await normalize("file:///x")
    assert result.mime == "text/plain"


@pytest.mark.asyncio
async def test_normalize_url_is_html():
    parsed = ParsedDoc(text="page", metadata={"type": "url"}, source="http://x")
    with patch(
        "archivum.store.normalize.parse_source",
        new=AsyncMock(return_value=parsed),
    ):
        result = await normalize("https://example.com")
    assert result.mime == "text/html"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_normalize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.normalize'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/normalize.py`:

```python
"""Normalization: adapt existing parsers into a NormalizedDoc (text + mime)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from archivum.ingest.parsers import parse_source

_TYPE_TO_MIME: dict[str, str] = {
    "md": "text/markdown",
    "txt": "text/plain",
    "text": "text/plain",
    "rst": "text/x-rst",
    "pdf": "application/pdf",
    "html": "text/html",
    "url": "text/html",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "json": "application/json",
    "jsonl": "application/jsonl",
    "epub": "application/epub+zip",
    "code": "text/x-code",
    "eml": "message/rfc822",
    "mbox": "application/mbox",
    "image": "image/*",
    "audio": "audio/*",
    "video": "video/*",
}


@dataclass(frozen=True, slots=True)
class NormalizedDoc:
    text: str
    mime: str
    metadata: dict[str, Any]


async def normalize(origin_uri: str) -> NormalizedDoc:
    """Parse `origin_uri` into normalized text and a mime type."""
    parsed = await parse_source(origin_uri)
    doc_type = str(parsed.metadata.get("type", "")).lower()
    mime = _TYPE_TO_MIME.get(doc_type, "text/plain")
    return NormalizedDoc(text=parsed.text, mime=mime, metadata=dict(parsed.metadata))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_normalize.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/normalize.py tests/store/test_normalize.py
git commit -m "feat(store): add normalization adapter over existing parsers"
```

---

## Task 9: SourceStore repository — inserts

**Files:**
- Create: `apps/backend/archivum/store/repository.py`
- Test: `tests/store/test_repository.py` (insert cases)

**Interfaces:**
- Consumes: `get_db` from `archivum.db.sqlite`; models `Source`, `Document`, `Chunk` from Task 4.
- Produces `class SourceStore` with (all async):
  - `insert_source(self, source: Source) -> None`.
  - `insert_document(self, document: Document) -> None`.
  - `insert_chunk(self, chunk: Chunk) -> None`.
  - `get_source(self, source_id: str) -> Source | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_repository.py`:

```python
"""Tests for SourceStore CRUD (real in-memory-style DB via temp file)."""

from __future__ import annotations

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.models import Chunk, Document, Source
from archivum.store.repository import SourceStore
from archivum.store.source_types import SourceType


@pytest.fixture
async def store(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db")
    await sqlite_mod.init_db(settings)
    return SourceStore()


def _make_source(**over) -> Source:
    base = dict(
        id="s" * 32, content_hash="h" * 64, version=1,
        source_type=SourceType.DOCUMENT, origin_uri="file:///x.txt",
        scope="personal", ingested_at="t", recorded_at="t",
        valid_from="t", valid_to=None,
    )
    base.update(over)
    return Source(**base)


@pytest.mark.asyncio
async def test_insert_and_get_source(store):
    src = _make_source()
    await store.insert_source(src)
    fetched = await store.get_source(src.id)
    assert fetched == src


@pytest.mark.asyncio
async def test_get_missing_source_returns_none(store):
    assert await store.get_source("nope") is None


@pytest.mark.asyncio
async def test_insert_document_and_chunk(store):
    src = _make_source()
    await store.insert_source(src)
    doc = Document(id="d" * 32, source_id=src.id, mime="text/plain", normalized_hash="n" * 64)
    await store.insert_document(doc)
    chunk = Chunk(id="c" * 32, document_id=doc.id, seq=0, start_offset=0, end_offset=4, text_hash="t" * 64)
    await store.insert_chunk(chunk)
    # No exception == rows persisted under FK constraints.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_repository.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.repository'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/repository.py`:

```python
"""SourceStore — async CRUD over the L1 evidence-lineage tables."""

from __future__ import annotations

from archivum.db.sqlite import get_db
from archivum.store.models import Chunk, Document, Source
from archivum.store.source_types import SourceType


def _row_to_source(row) -> Source:
    return Source(
        id=row["id"],
        content_hash=row["content_hash"],
        version=row["version"],
        source_type=SourceType(row["source_type"]),
        origin_uri=row["origin_uri"],
        scope=row["scope"],
        ingested_at=row["ingested_at"],
        recorded_at=row["recorded_at"],
        valid_from=row["valid_from"],
        valid_to=row["valid_to"],
    )


class SourceStore:
    """Async repository over sources/documents/chunks (L1)."""

    async def insert_source(self, source: Source) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO sources "
                "(id, content_hash, version, source_type, origin_uri, scope, "
                " ingested_at, recorded_at, valid_from, valid_to) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    source.id, source.content_hash, source.version,
                    source.source_type.value, source.origin_uri, source.scope,
                    source.ingested_at, source.recorded_at, source.valid_from,
                    source.valid_to,
                ),
            )
            await db.commit()

    async def insert_document(self, document: Document) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO documents (id, source_id, mime, normalized_hash) "
                "VALUES (?,?,?,?)",
                (document.id, document.source_id, document.mime, document.normalized_hash),
            )
            await db.commit()

    async def insert_chunk(self, chunk: Chunk) -> None:
        async with get_db() as db:
            await db.execute(
                "INSERT INTO chunks "
                "(id, document_id, seq, start_offset, end_offset, text_hash) "
                "VALUES (?,?,?,?,?,?)",
                (
                    chunk.id, chunk.document_id, chunk.seq,
                    chunk.start_offset, chunk.end_offset, chunk.text_hash,
                ),
            )
            await db.commit()

    async def get_source(self, source_id: str) -> Source | None:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM sources WHERE id=?", (source_id,)
            ) as cur:
                row = await cur.fetchone()
                return _row_to_source(row) if row else None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_repository.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/repository.py tests/store/test_repository.py
git commit -m "feat(store): add SourceStore inserts and get_source"
```

---

## Task 10: SourceStore — dedup lookup and version resolution

**Files:**
- Modify: `apps/backend/archivum/store/repository.py` (add methods to `SourceStore`).
- Test: `tests/store/test_repository_versioning.py`

**Interfaces:**
- Consumes: same as Task 9.
- Produces (added to `SourceStore`):
  - `get_source_by_hash_and_version(self, content_hash: str, version: int) -> Source | None` — dedup lookup for an exact `(content_hash, version)`.
  - `latest_version_for_origin(self, origin_uri: str) -> int` — highest existing `version` for an `origin_uri`, or `0` if none.
  - `get_document_for_source(self, source_id: str) -> Document | None`.
  - `list_chunks(self, document_id: str) -> list[Chunk]` — ordered by `seq`.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_repository_versioning.py`:

```python
"""Tests for dedup + version-resolution helpers on SourceStore."""

from __future__ import annotations

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.models import Chunk, Document, Source
from archivum.store.repository import SourceStore
from archivum.store.source_types import SourceType


@pytest.fixture
async def store(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db")
    await sqlite_mod.init_db(settings)
    return SourceStore()


def _src(sid: str, content_hash: str, version: int, origin: str) -> Source:
    return Source(
        id=sid, content_hash=content_hash, version=version,
        source_type=SourceType.DOCUMENT, origin_uri=origin, scope="personal",
        ingested_at="t", recorded_at="t", valid_from="t", valid_to=None,
    )


@pytest.mark.asyncio
async def test_dedup_lookup_by_hash_and_version(store):
    src = _src("s1", "a" * 64, 1, "file:///x")
    await store.insert_source(src)
    assert await store.get_source_by_hash_and_version("a" * 64, 1) == src
    assert await store.get_source_by_hash_and_version("a" * 64, 2) is None


@pytest.mark.asyncio
async def test_latest_version_for_origin(store):
    assert await store.latest_version_for_origin("file:///x") == 0
    await store.insert_source(_src("s1", "a" * 64, 1, "file:///x"))
    await store.insert_source(_src("s2", "b" * 64, 2, "file:///x"))
    assert await store.latest_version_for_origin("file:///x") == 2


@pytest.mark.asyncio
async def test_document_and_chunks_readback(store):
    src = _src("s1", "a" * 64, 1, "file:///x")
    await store.insert_source(src)
    doc = Document(id="d1", source_id="s1", mime="text/plain", normalized_hash="n" * 64)
    await store.insert_document(doc)
    await store.insert_chunk(Chunk(id="c1", document_id="d1", seq=1, start_offset=5, end_offset=9, text_hash="t" * 64))
    await store.insert_chunk(Chunk(id="c0", document_id="d1", seq=0, start_offset=0, end_offset=4, text_hash="u" * 64))
    assert await store.get_document_for_source("s1") == doc
    chunks = await store.list_chunks("d1")
    assert [c.seq for c in chunks] == [0, 1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_repository_versioning.py -v`
Expected: FAIL with `AttributeError: 'SourceStore' object has no attribute 'get_source_by_hash_and_version'`

- [ ] **Step 3: Write minimal implementation**

In `apps/backend/archivum/store/repository.py`, add a `_row_to_document` and `_row_to_chunk` helper near `_row_to_source`:

```python
def _row_to_document(row) -> Document:
    return Document(
        id=row["id"],
        source_id=row["source_id"],
        mime=row["mime"],
        normalized_hash=row["normalized_hash"],
    )


def _row_to_chunk(row) -> Chunk:
    return Chunk(
        id=row["id"],
        document_id=row["document_id"],
        seq=row["seq"],
        start_offset=row["start_offset"],
        end_offset=row["end_offset"],
        text_hash=row["text_hash"],
    )
```

Then add these methods to `SourceStore`:

```python
    async def get_source_by_hash_and_version(
        self, content_hash: str, version: int
    ) -> Source | None:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM sources WHERE content_hash=? AND version=?",
                (content_hash, version),
            ) as cur:
                row = await cur.fetchone()
                return _row_to_source(row) if row else None

    async def latest_version_for_origin(self, origin_uri: str) -> int:
        async with get_db() as db:
            async with db.execute(
                "SELECT MAX(version) AS v FROM sources WHERE origin_uri=?",
                (origin_uri,),
            ) as cur:
                row = await cur.fetchone()
                return int(row["v"]) if row and row["v"] is not None else 0

    async def get_document_for_source(self, source_id: str) -> Document | None:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM documents WHERE source_id=? LIMIT 1", (source_id,)
            ) as cur:
                row = await cur.fetchone()
                return _row_to_document(row) if row else None

    async def list_chunks(self, document_id: str) -> list[Chunk]:
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM chunks WHERE document_id=? ORDER BY seq ASC",
                (document_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [_row_to_chunk(r) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_repository_versioning.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/repository.py tests/store/test_repository_versioning.py
git commit -m "feat(store): add dedup + version resolution to SourceStore"
```

---

## Task 11: add blob_dir config setting

**Files:**
- Modify: `apps/backend/archivum/config.py:32-36` (data paths block).
- Test: `tests/store/test_config_blob_dir.py`

**Interfaces:**
- Consumes: existing `Settings`.
- Produces: `Settings.blob_dir: Path` defaulting to `Path("/data/blobs")`.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_config_blob_dir.py`:

```python
"""Settings must expose a blob_dir path for the L0 store."""

from __future__ import annotations

from pathlib import Path

from archivum.config import Settings


def test_default_blob_dir():
    assert Settings().blob_dir == Path("/data/blobs")


def test_blob_dir_is_overridable(tmp_path):
    s = Settings(blob_dir=tmp_path / "blobs")
    assert s.blob_dir == tmp_path / "blobs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_config_blob_dir.py -v`
Expected: FAIL — `AttributeError`/validation error (`blob_dir` unknown).

- [ ] **Step 3: Write minimal implementation**

In `apps/backend/archivum/config.py`, inside the `# ── Data paths ──` block (after the `raw_dir` line, around line 34), add:

```python
    blob_dir: Path = Path("/data/blobs")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_config_blob_dir.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/config.py tests/store/test_config_blob_dir.py
git commit -m "feat(config): add blob_dir data path for L0 store"
```

---

## Task 12: ingest_source() orchestration

**Files:**
- Create: `apps/backend/archivum/store/ingest.py`
- Test: `tests/store/test_ingest.py`

**Interfaces:**
- Consumes: `BlobStore` (Task 2), `detect_source_type`/`SourceType` (Task 3), models + `new_id` (Task 4), `chunk_text` (Task 7), `normalize` (Task 8), `SourceStore` (Tasks 9-10), `sha256_bytes`/`sha256_text` (Task 1).
- Produces:
  - `async def ingest_source(*, origin_uri: str, raw_bytes: bytes, scope: str = "personal", explicit_type: SourceType | str | None = None, store: SourceStore | None = None, blob_store: BlobStore | None = None, settings: Settings | None = None) -> IngestResult`
    - Content-addresses `raw_bytes` (blob `put`), computes the new version as `latest_version_for_origin(origin_uri) + 1`, dedups on exact `(content_hash, version)` — if the same bytes are re-ingested at the same origin, returns the existing `IngestResult` with `deduplicated=True` and creates **no new row/version**; a *changed* source (new `content_hash`) always creates a new version. Parses via `normalize`, chunks, and persists `Source`/`Document`/`Chunk` rows. Never mutates existing rows or blobs.
    - `IngestResult` returned as defined in Task 4.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_ingest.py`:

```python
"""Orchestration + invariant tests for ingest_source()."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.ingest import ingest_source
from archivum.store.normalize import NormalizedDoc
from archivum.store.repository import SourceStore


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return settings, SourceStore(), BlobStore(settings.blob_dir)


def _patch_normalize(text: str, mime: str = "text/plain"):
    return patch(
        "archivum.store.ingest.normalize",
        new=AsyncMock(return_value=NormalizedDoc(text=text, mime=mime, metadata={})),
    )


@pytest.mark.asyncio
async def test_ingest_creates_source_document_chunks(env):
    settings, store, blobs = env
    with _patch_normalize("Hello body text."):
        result = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"Hello body text.",
            store=store, blob_store=blobs, settings=settings,
        )
    assert result.source.version == 1
    assert result.deduplicated is False
    assert result.document.mime == "text/plain"
    assert len(result.chunks) >= 1
    # Blob is content-addressed under the raw bytes.
    assert blobs.exists(result.source.content_hash)


@pytest.mark.asyncio
async def test_reingest_identical_bytes_is_deduplicated(env):
    settings, store, blobs = env
    with _patch_normalize("same content"):
        first = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"same content",
            store=store, blob_store=blobs, settings=settings,
        )
    with _patch_normalize("same content"):
        second = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"same content",
            store=store, blob_store=blobs, settings=settings,
        )
    assert second.deduplicated is True
    assert second.source.id == first.source.id
    assert second.source.version == 1
    assert await store.latest_version_for_origin("file:///a.txt") == 1


@pytest.mark.asyncio
async def test_reingest_changed_bytes_creates_new_version(env):
    settings, store, blobs = env
    with _patch_normalize("v1 body"):
        v1 = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"v1 body",
            store=store, blob_store=blobs, settings=settings,
        )
    with _patch_normalize("v2 body changed"):
        v2 = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"v2 body changed",
            store=store, blob_store=blobs, settings=settings,
        )
    assert v1.source.version == 1
    assert v2.source.version == 2
    assert v2.deduplicated is False
    # Old version is still intact and unmutated (immutability).
    old = await store.get_source(v1.source.id)
    assert old == v1.source
    assert blobs.exists(v1.source.content_hash)
    assert blobs.exists(v2.source.content_hash)


@pytest.mark.asyncio
async def test_evidence_blob_is_never_overwritten(env):
    settings, store, blobs = env
    with _patch_normalize("original"):
        r = await ingest_source(
            origin_uri="file:///a.txt", raw_bytes=b"original",
            store=store, blob_store=blobs, settings=settings,
        )
    assert blobs.get(r.source.content_hash) == b"original"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/store/test_ingest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.store.ingest'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/store/ingest.py`:

```python
"""Deterministic ingestion stage: content-address → dedup/version → parse →
chunk → persist. Evidence (L0) is immutable; re-ingest creates new versions."""

from __future__ import annotations

from datetime import UTC, datetime

from archivum.config import Settings, get_settings
from archivum.store.blobs import BlobStore
from archivum.store.chunking import chunk_text
from archivum.store.hashing import sha256_bytes, sha256_text
from archivum.store.models import (
    Chunk,
    Document,
    IngestResult,
    Source,
    new_id,
)
from archivum.store.normalize import normalize
from archivum.store.repository import SourceStore
from archivum.store.source_types import SourceType, detect_source_type


async def ingest_source(
    *,
    origin_uri: str,
    raw_bytes: bytes,
    scope: str = "personal",
    explicit_type: SourceType | str | None = None,
    store: SourceStore | None = None,
    blob_store: BlobStore | None = None,
    settings: Settings | None = None,
) -> IngestResult:
    """Ingest one source deterministically. Returns an IngestResult.

    Idempotent per (origin_uri, content_hash): identical re-ingest is a no-op
    that returns the existing rows with deduplicated=True. Changed bytes always
    produce a new version; existing rows and blobs are never mutated.
    """
    s = settings or get_settings()
    store = store or SourceStore()
    blob_store = blob_store or BlobStore(s.blob_dir)

    content_hash = sha256_bytes(raw_bytes)

    # Dedup: if this exact content already exists for this origin, no-op.
    existing_version = await _existing_version(store, origin_uri, content_hash)
    if existing_version is not None:
        existing = await store.get_source_by_hash_and_version(content_hash, existing_version)
        assert existing is not None
        document = await store.get_document_for_source(existing.id)
        assert document is not None
        chunks = await store.list_chunks(document.id)
        return IngestResult(
            source=existing, document=document, chunks=chunks, deduplicated=True
        )

    # New version = one past the highest existing for this origin.
    version = await store.latest_version_for_origin(origin_uri) + 1

    # L0: write raw evidence once (content-addressed).
    blob_store.put(raw_bytes)

    # Normalize (parse) into text + mime.
    normalized = await normalize(origin_uri)
    normalized_hash = sha256_text(normalized.text)

    now = datetime.now(UTC).isoformat()
    source_type = detect_source_type(
        origin_uri=origin_uri, mime=normalized.mime, explicit=explicit_type
    )

    source = Source(
        id=new_id(),
        content_hash=content_hash,
        version=version,
        source_type=source_type,
        origin_uri=origin_uri,
        scope=scope,
        ingested_at=now,
        recorded_at=now,
        valid_from=now,
        valid_to=None,
    )
    await store.insert_source(source)

    document = Document(
        id=new_id(),
        source_id=source.id,
        mime=normalized.mime,
        normalized_hash=normalized_hash,
    )
    await store.insert_document(document)

    chunks: list[Chunk] = []
    for spec in chunk_text(normalized.text):
        chunk = Chunk(
            id=new_id(),
            document_id=document.id,
            seq=spec.seq,
            start_offset=spec.start_offset,
            end_offset=spec.end_offset,
            text_hash=sha256_text(spec.text),
        )
        await store.insert_chunk(chunk)
        chunks.append(chunk)

    return IngestResult(
        source=source, document=document, chunks=chunks, deduplicated=False
    )


async def _existing_version(
    store: SourceStore, origin_uri: str, content_hash: str
) -> int | None:
    """Return the version at which this exact content already exists for the
    origin, or None. Scans existing versions for a content_hash match."""
    latest = await store.latest_version_for_origin(origin_uri)
    for version in range(1, latest + 1):
        match = await store.get_source_by_hash_and_version(content_hash, version)
        if match is not None and match.origin_uri == origin_uri:
            return version
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/store/test_ingest.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/store/ingest.py tests/store/test_ingest.py
git commit -m "feat(store): add deterministic ingest_source orchestration"
```

---

## Task 13: sources API router

**Files:**
- Create: `apps/backend/archivum/api/sources.py`
- Test: `tests/api/test_sources.py`

**Interfaces:**
- Consumes: `ingest_source` (Task 12), `SourceStore` (Tasks 9-10), `require_writer`/`CurrentUser` from `archivum.auth`, `get_settings`.
- Produces:
  - `router = APIRouter(prefix="/api/sources", tags=["sources"])`.
  - `POST /api/sources/ingest` body `SourceIngestRequest(origin_uri: str, scope: str = "personal", source_type: str | None = None)` → `SourceResponse(id, content_hash, version, source_type, origin_uri, scope, deduplicated, chunk_count)`. The endpoint reads `raw_bytes` from `origin_uri` via `parse_source`-adjacent path; for this task, it fetches bytes with `_read_bytes(origin_uri)` (files read from disk, `http(s)` fetched via `httpx`).
  - `GET /api/sources/{source_id}` → `SourceDetailResponse(source: SourceResponse, chunk_count: int)` or 404.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_sources.py`:

```python
"""Tests for the /api/sources router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from archivum.auth import CurrentUser, require_writer
from archivum.store.models import Chunk, Document, IngestResult, Source
from archivum.store.source_types import SourceType


def _fake_result(deduplicated=False) -> IngestResult:
    src = Source(
        id="s" * 32, content_hash="h" * 64, version=1,
        source_type=SourceType.DOCUMENT, origin_uri="file:///a.txt",
        scope="personal", ingested_at="t", recorded_at="t",
        valid_from="t", valid_to=None,
    )
    doc = Document(id="d" * 32, source_id=src.id, mime="text/plain", normalized_hash="n" * 64)
    chunk = Chunk(id="c" * 32, document_id=doc.id, seq=0, start_offset=0, end_offset=3, text_hash="t" * 64)
    return IngestResult(source=src, document=doc, chunks=[chunk], deduplicated=deduplicated)


@pytest.fixture
def writer_client(app_client):
    from archivum.main import create_app  # app already built by app_client
    app_client.app.dependency_overrides[require_writer] = lambda: CurrentUser(
        username="admin", role="owner", wiki_id="default"
    )
    yield app_client
    app_client.app.dependency_overrides.pop(require_writer, None)


def test_ingest_endpoint_returns_source(writer_client):
    with patch(
        "archivum.api.sources._read_bytes",
        new=AsyncMock(return_value=b"hello"),
    ), patch(
        "archivum.api.sources.ingest_source",
        new=AsyncMock(return_value=_fake_result()),
    ):
        resp = writer_client.post(
            "/api/sources/ingest", json={"origin_uri": "file:///a.txt"}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["version"] == 1
    assert body["deduplicated"] is False
    assert body["chunk_count"] == 1


def test_ingest_endpoint_reports_dedup(writer_client):
    with patch(
        "archivum.api.sources._read_bytes",
        new=AsyncMock(return_value=b"hello"),
    ), patch(
        "archivum.api.sources.ingest_source",
        new=AsyncMock(return_value=_fake_result(deduplicated=True)),
    ):
        resp = writer_client.post(
            "/api/sources/ingest", json={"origin_uri": "file:///a.txt"}
        )
    assert resp.json()["deduplicated"] is True


def test_get_source_404(writer_client):
    with patch(
        "archivum.api.sources.SourceStore.get_source",
        new=AsyncMock(return_value=None),
    ):
        resp = writer_client.get("/api/sources/nope")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/api/test_sources.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'archivum.api.sources'`

- [ ] **Step 3: Write minimal implementation**

Create `apps/backend/archivum/api/sources.py`:

```python
"""Sources routes: /api/sources/* — deterministic ingestion + read-back."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from archivum.auth import CurrentUser, require_writer
from archivum.config import Settings, get_settings
from archivum.store.ingest import ingest_source
from archivum.store.models import IngestResult, Source
from archivum.store.repository import SourceStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sources", tags=["sources"])


class SourceIngestRequest(BaseModel):
    origin_uri: str
    scope: str = "personal"
    source_type: str | None = None


class SourceResponse(BaseModel):
    id: str
    content_hash: str
    version: int
    source_type: str
    origin_uri: str
    scope: str
    deduplicated: bool
    chunk_count: int


class SourceDetailResponse(BaseModel):
    source: SourceResponse
    chunk_count: int


async def _read_bytes(origin_uri: str) -> bytes:
    """Fetch the raw bytes for an origin (local file path/URI or http(s))."""
    parsed = urlparse(origin_uri)
    if parsed.scheme in ("http", "https"):
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(origin_uri)
            resp.raise_for_status()
            return resp.content
    path = Path(parsed.path if parsed.scheme == "file" else origin_uri)
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"detail": f"cannot read source: {origin_uri}", "code": "unreadable_source"},
        )
    return path.read_bytes()


def _to_response(result: IngestResult) -> SourceResponse:
    return SourceResponse(
        id=result.source.id,
        content_hash=result.source.content_hash,
        version=result.source.version,
        source_type=result.source.source_type.value,
        origin_uri=result.source.origin_uri,
        scope=result.source.scope,
        deduplicated=result.deduplicated,
        chunk_count=len(result.chunks),
    )


@router.post("/ingest", response_model=SourceResponse)
async def ingest_endpoint(
    body: SourceIngestRequest,
    current_user: CurrentUser = Depends(require_writer),
    settings: Settings = Depends(get_settings),
) -> SourceResponse:
    logger.info("API sources.ingest", extra={"origin_uri": body.origin_uri})
    raw_bytes = await _read_bytes(body.origin_uri)
    result = await ingest_source(
        origin_uri=body.origin_uri,
        raw_bytes=raw_bytes,
        scope=body.scope,
        explicit_type=body.source_type,
        settings=settings,
    )
    return _to_response(result)


@router.get("/{source_id}", response_model=SourceDetailResponse)
async def get_source_endpoint(
    source_id: str,
    current_user: CurrentUser = Depends(require_writer),
) -> SourceDetailResponse:
    store = SourceStore()
    source: Source | None = await store.get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"detail": "source not found", "code": "source_not_found"},
        )
    document = await store.get_document_for_source(source.id)
    chunk_count = len(await store.list_chunks(document.id)) if document else 0
    return SourceDetailResponse(
        source=SourceResponse(
            id=source.id,
            content_hash=source.content_hash,
            version=source.version,
            source_type=source.source_type.value,
            origin_uri=source.origin_uri,
            scope=source.scope,
            deduplicated=False,
            chunk_count=chunk_count,
        ),
        chunk_count=chunk_count,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/api/test_sources.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/archivum/api/sources.py tests/api/test_sources.py
git commit -m "feat(api): add /api/sources ingest and read-back routes"
```

---

## Task 14: register router + configure blob store on startup

**Files:**
- Modify: `apps/backend/archivum/main.py` (imports + `create_app` router registration + startup config).
- Test: `tests/api/test_sources_registered.py`

**Interfaces:**
- Consumes: `sources` router (Task 13), `Settings.blob_dir` (Task 11), `BlobStore` (Task 2).
- Produces: `create_app()` mounts `/api/sources/*`; the blob directory is created at startup.

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_sources_registered.py`:

```python
"""The sources router must be mounted on the app."""

from __future__ import annotations


def test_sources_ingest_route_exists(app_client):
    paths = {route.path for route in app_client.app.routes}
    assert "/api/sources/ingest" in paths
    assert "/api/sources/{source_id}" in paths
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --project apps/backend pytest tests/api/test_sources_registered.py -v`
Expected: FAIL — `/api/sources/ingest` not in mounted paths.

- [ ] **Step 3: Add the import**

In `apps/backend/archivum/main.py`, alongside the other `from archivum.api import ... as ..._routes` lines, add:

```python
from archivum.api import sources as sources_routes
```

- [ ] **Step 4: Register the router in create_app**

Find the block in `create_app` where routers are included (the existing `app.include_router(...)` calls) and add:

```python
    app.include_router(sources_routes.router)
```

- [ ] **Step 5: Create the blob directory at startup**

In the app's lifespan/startup section of `main.py` where `sqlite.init_db(settings)` is awaited, add immediately after it:

```python
    settings.blob_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run --project apps/backend pytest tests/api/test_sources_registered.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Commit**

```bash
git add apps/backend/archivum/main.py tests/api/test_sources_registered.py
git commit -m "feat(api): mount sources router and provision blob dir on startup"
```

---

## Task 15: end-to-end invariant test (full stack, no mocks on parse for a text file)

**Files:**
- Test: `tests/store/test_ingest_e2e.py`

**Interfaces:**
- Consumes: `ingest_source` (Task 12), `SourceStore` (Tasks 9-10), `BlobStore` (Task 2) — exercised against a real temp SQLite DB, real blob dir, and the real `normalize` path over a real `.txt` file (which `archivum.ingest.parsers.parse_file` handles with no external deps).
- Produces: proof that L0 immutability, dedup, versioning, and provenance (chunk `text_hash` matches blob-derived normalized text) hold end-to-end.

- [ ] **Step 1: Write the failing test**

Create `tests/store/test_ingest_e2e.py`:

```python
"""End-to-end deterministic ingestion over a real .txt file (no parser mocks)."""

from __future__ import annotations

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.hashing import sha256_text
from archivum.store.ingest import ingest_source
from archivum.store.repository import SourceStore


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return settings, SourceStore(), BlobStore(settings.blob_dir)


@pytest.mark.asyncio
async def test_full_ingest_of_text_file(env, tmp_path):
    settings, store, blobs = env
    doc_path = tmp_path / "notes.txt"
    body = "First paragraph.\n\nSecond paragraph with more words here."
    doc_path.write_text(body, encoding="utf-8")
    origin = str(doc_path)

    result = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )

    # L0: blob content is the exact raw bytes.
    assert blobs.get(result.source.content_hash) == body.encode("utf-8")
    # L1: document mime is plain text; chunks carry text hashes.
    assert result.document.mime == "text/plain"
    assert result.chunks
    for c in result.chunks:
        assert len(c.text_hash) == 64


@pytest.mark.asyncio
async def test_reingest_same_file_is_dedup_no_new_version(env, tmp_path):
    settings, store, blobs = env
    doc_path = tmp_path / "notes.txt"
    doc_path.write_text("stable content", encoding="utf-8")
    origin = str(doc_path)

    first = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )
    second = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )
    assert second.deduplicated is True
    assert second.source.id == first.source.id
    assert await store.latest_version_for_origin(origin) == 1


@pytest.mark.asyncio
async def test_edited_file_creates_v2_without_mutating_v1(env, tmp_path):
    settings, store, blobs = env
    doc_path = tmp_path / "notes.txt"
    doc_path.write_text("original body", encoding="utf-8")
    origin = str(doc_path)

    v1 = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )
    doc_path.write_text("edited body content", encoding="utf-8")
    v2 = await ingest_source(
        origin_uri=origin, raw_bytes=doc_path.read_bytes(),
        store=store, blob_store=blobs, settings=settings,
    )

    assert (v1.source.version, v2.source.version) == (1, 2)
    # v1 evidence and row are intact (immutability).
    assert await store.get_source(v1.source.id) == v1.source
    assert blobs.get(v1.source.content_hash) == b"original body"
    assert v1.source.content_hash != v2.source.content_hash
```

- [ ] **Step 2: Run test to verify it passes (no new impl needed)**

Run: `uv run --project apps/backend pytest tests/store/test_ingest_e2e.py -v`
Expected: PASS (3 passed). If any test fails, the failure indicates a real invariant bug in Tasks 2/12 — fix there, do not weaken the test.

- [ ] **Step 3: Run the full store + api suite**

Run: `uv run --project apps/backend pytest tests/store tests/api/test_sources.py tests/api/test_sources_registered.py -v`
Expected: PASS (all).

- [ ] **Step 4: Commit**

```bash
git add tests/store/test_ingest_e2e.py
git commit -m "test(store): add end-to-end evidence-immutability + versioning invariants"
```

---

## Task 16: full regression + coverage gate

**Files:**
- Test: entire suite (no new files).

**Interfaces:**
- Consumes: everything above.
- Produces: green full test run confirming no regression in existing modules.

- [ ] **Step 1: Run the complete test suite**

Run: `uv run --project apps/backend pytest -q`
Expected: PASS (all tests, including pre-existing ones — the additive schema and new router must not break `tests/db/test_sqlite.py`, `tests/api/*`, or `tests/ingest/*`).

- [ ] **Step 2: If any pre-existing test broke, fix the regression**

Common cause: `init_db` now applies `EVIDENCE_SCHEMA`. If a test patches `db.executescript`, ensure it still tolerates two calls. Fix the code (not the test) unless the test asserted an obsolete single-call contract; in that case update the assertion to expect both schema scripts. Re-run `uv run --project apps/backend pytest -q` until green.

- [ ] **Step 3: Commit any regression fixes**

```bash
git add -A
git commit -m "test: keep full suite green after evidence-store additions"
```

---

## Interfaces consumed by later epics (317/318/319)

These are the stable Produces contracts downstream epics build on. Do not rename without a migration.

- **`SourceStore`** (`archivum.store.repository`): `insert_source`, `insert_document`, `insert_chunk`, `get_source`, `get_source_by_hash_and_version`, `latest_version_for_origin`, `get_document_for_source`, `list_chunks`. Knowledge extractors (317/318) read `Chunk` rows as evidence anchors and cite `chunk.id` + `(start_offset, end_offset)`.
- **`ingest_source(...) -> IngestResult`** (`archivum.store.ingest`): the single deterministic-stage entrypoint. 316 (conversation capture) and 318 (Archgraph) call it to land raw evidence and get back stable `Source`/`Document`/`Chunk` ids.
- **Models** (`archivum.store.models`): `Source`, `Document`, `Chunk`, `IngestResult`, `ExtractionMethod`, `new_id`. `ExtractionMethod ∈ {EXTRACTED, INFERRED, AMBIGUOUS}` is the provenance vocabulary every future knowledge object references.
- **Schema** (`archivum.store.schema.EVIDENCE_SCHEMA`): the L1 `sources`/`documents`/`chunks` tables 317 extends with entity/claim/relationship tables (foreign-keying `chunks.id` for provenance).

---

## Self-Review

**1. Spec coverage.**
- L0 content-addressed sha256 blob store, write-once, dedup → Tasks 1, 2. ✔
- Versioning (re-ingest = new version, never mutate) → Tasks 10, 12, 15. ✔ (spec §2 L0)
- L1 `Source`/`Document`/`Chunk` with `content_hash`/`version`/`source_type`/`origin_uri`/`scope`/bitemporal fields → Tasks 4, 5. ✔ (spec §4)
- `extraction_method ∈ {EXTRACTED,INFERRED,AMBIGUOUS}` → `ExtractionMethod`, Task 4. ✔ (spec §4)
- Source-type registry over the spec's eight source kinds → Task 3. ✔ (spec §4)
- Normalization/parse dispatch reusing existing parsers → Task 8. ✔ (spec §5 deterministic stage)
- Chunking with span anchors → Task 7. ✔ (spec §4 Chunk `span`)
- Ingestion orchestration API endpoint → Tasks 12, 13, 14. ✔ (spec §5)
- Invariant tests (immutability, dedup, re-ingest new version) → Tasks 12, 15. ✔ (spec §6.1)
- Links back to originals (`origin_uri`, `content_hash`) → Task 4/5 columns. ✔ (spec §4)
- Generated knowledge never overwrites evidence — enforced by write-once blob store + additive versioned rows; documented in Global Constraints. ✔ (spec §6.1)
- Indexes rebuildable — no canonical data placed in L2; noted in Global Constraints. ✔ (spec §6.6)
- Deferred out of scope (correctly, per epic boundary): agent-worker stage, Qdrant/Kuzu/FTS index writes, Archgraph tree-sitter extractor, wiki_data import — these belong to 316/317/318/319, not PER-315.

**2. Placeholder scan.** No "TBD"/"add validation"/"similar to Task N"/"handle edge cases" strings; every code step shows real code and exact commands. ✔

**3. Type consistency.** `Source`/`Document`/`Chunk`/`IngestResult` field names are identical across Tasks 4, 5, 9, 10, 12, 13, 15. `SourceStore` method names match between definition (Tasks 9-10) and callers (Tasks 12, 13). `NormalizedDoc(text, mime, metadata)` consistent across Tasks 8, 12. `ChunkSpec(seq, start_offset, end_offset, text)` consistent Tasks 7, 12. `BlobStore.put/get/exists/path_for` consistent Tasks 2, 12, 13, 15. `detect_source_type(origin_uri=, mime=, explicit=)` consistent Tasks 3, 12. ✔

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-28-per315-immutable-source-store-and-ingestion.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
