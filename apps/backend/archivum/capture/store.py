"""CaptureStore: write a Conversation to L0 (content-addressed evidence) and
L1 (Source -> Document -> one Chunk per turn) reusing PER-315 primitives.
Idempotent per (origin, content_hash); never mutates existing rows/blobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from archivum.capture.canonical import content_hash, to_canonical_bytes
from archivum.capture.redaction import redact_turn_text
from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.capture.transcript import render_transcript
from archivum.config import Settings, get_settings
from archivum.store.blobs import BlobStore
from archivum.store.hashing import sha256_text
from archivum.store.models import Chunk, Document, Source, new_id
from archivum.store.repository import SourceStore
from archivum.store.source_types import SourceType


def _redact_conversation(conv: Conversation) -> Conversation:
    """Return a new Conversation with hidden reasoning stripped from all Turn text and ToolCall results."""
    import dataclasses

    redacted_turns: list[Turn] = []
    for turn in conv.turns:
        redacted_tcs = tuple(
            dataclasses.replace(tc, result=None if tc.result is None else redact_turn_text(tc.result))
            for tc in turn.tool_calls
        )
        redacted_turns.append(dataclasses.replace(turn, text=redact_turn_text(turn.text), tool_calls=redacted_tcs))
    return dataclasses.replace(conv, turns=tuple(redacted_turns))


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
        conv = _redact_conversation(conv)
        raw = to_canonical_bytes(conv)
        chash = content_hash(conv)
        origin = conv.origin_uri or f"conversation:{conv.interface}:{conv.session_id}"

        existing = await self._existing(origin, chash)
        if existing is not None:
            return await self._dedup_result(existing, chash)

        self._blobs.put(raw)  # L0 evidence, write-once (content-addressed, idempotent)
        now = datetime.now(UTC).isoformat()

        # Build the full L1 lineage with pre-generated ids, then persist it in one
        # transaction so a crash can never leave a source without its doc/chunks.
        text, spans = render_transcript(conv)
        source_id = new_id()
        document = Document(
            id=new_id(), source_id=source_id, mime="text/plain",
            normalized_hash=sha256_text(text),
        )
        chunks = [
            Chunk(
                id=new_id(), document_id=document.id, seq=seq,
                start_offset=start, end_offset=end, text_hash=sha256_text(block),
            )
            for seq, (start, end, block) in enumerate(spans)
        ]
        source, created = await self._store.create_source_with_lineage(
            id=source_id, content_hash=chash, source_type=SourceType.CONVERSATION,
            origin_uri=origin, scope=conv.scope, ingested_at=now, recorded_at=now,
            valid_from=conv.started_at or now, valid_to=None,
            document=document, chunks=chunks,
        )
        if not created:
            # A concurrent capture of identical content won the version race; reuse it.
            return await self._dedup_result(source, chash)

        return CaptureResult(
            source_id=source.id, content_hash=chash, version=source.version,
            document_id=document.id, chunk_ids=tuple(c.id for c in chunks),
            deduplicated=False,
        )

    async def _existing(self, origin: str, chash: str) -> Source | None:
        return await self._store.get_source_by_origin_and_hash(origin, chash)

    async def _dedup_result(self, source: Source, chash: str) -> CaptureResult:
        """Build a deduplicated CaptureResult by reading back an existing
        source's document and chunks."""
        document = await self._store.get_document_for_source(source.id)
        if document is None:
            raise RuntimeError(
                f"source {source.id!r} exists but has no associated document — "
                "store is inconsistent"
            )
        chunks = await self._store.list_chunks(document.id)
        return CaptureResult(
            source_id=source.id, content_hash=chash, version=source.version,
            document_id=document.id, chunk_ids=tuple(c.id for c in chunks),
            deduplicated=True,
        )
