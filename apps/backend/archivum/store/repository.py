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
