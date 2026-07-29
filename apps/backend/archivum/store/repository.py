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

    async def get_source_by_origin_and_hash(
        self, origin_uri: str, content_hash: str
    ) -> Source | None:
        """Return the source for this exact (origin_uri, content_hash) in one
        indexed query (highest version if duplicates ever exist), else None."""
        async with get_db() as db:
            async with db.execute(
                "SELECT * FROM sources WHERE origin_uri=? AND content_hash=? "
                "ORDER BY version DESC LIMIT 1",
                (origin_uri, content_hash),
            ) as cur:
                row = await cur.fetchone()
                return _row_to_source(row) if row else None

    async def create_source_with_lineage(
        self,
        *,
        id: str,
        content_hash: str,
        source_type: SourceType,
        origin_uri: str,
        scope: str,
        ingested_at: str,
        recorded_at: str,
        valid_from: str,
        valid_to: str | None,
        document: Document,
        chunks: list[Chunk],
    ) -> tuple[Source, bool]:
        """Atomically dedup-or-insert a source AND its full L1 lineage.

        Returns (source, created). If an identical source already exists for
        (origin_uri, content_hash) it is returned with created=False and the
        supplied document/chunks are discarded. Otherwise assigns
        version = MAX+1 and inserts the source, its document, and every chunk
        inside a single BEGIN IMMEDIATE transaction — so a crash can never
        leave a source without its document/chunks, and concurrent writers for
        the same origin cannot collide on UNIQUE(origin_uri, version).
        """
        async with get_db() as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                async with db.execute(
                    "SELECT * FROM sources WHERE origin_uri=? AND content_hash=? "
                    "ORDER BY version DESC LIMIT 1",
                    (origin_uri, content_hash),
                ) as cur:
                    row = await cur.fetchone()
                if row is not None:
                    await db.commit()
                    return _row_to_source(row), False

                async with db.execute(
                    "SELECT MAX(version) AS v FROM sources WHERE origin_uri=?",
                    (origin_uri,),
                ) as cur:
                    r = await cur.fetchone()
                    version = (int(r["v"]) if r and r["v"] is not None else 0) + 1

                await db.execute(
                    "INSERT INTO sources "
                    "(id, content_hash, version, source_type, origin_uri, scope, "
                    " ingested_at, recorded_at, valid_from, valid_to) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        id, content_hash, version, source_type.value, origin_uri,
                        scope, ingested_at, recorded_at, valid_from, valid_to,
                    ),
                )
                await db.execute(
                    "INSERT INTO documents (id, source_id, mime, normalized_hash) "
                    "VALUES (?,?,?,?)",
                    (document.id, document.source_id, document.mime,
                     document.normalized_hash),
                )
                for chunk in chunks:
                    await db.execute(
                        "INSERT INTO chunks "
                        "(id, document_id, seq, start_offset, end_offset, text_hash) "
                        "VALUES (?,?,?,?,?,?)",
                        (chunk.id, chunk.document_id, chunk.seq, chunk.start_offset,
                         chunk.end_offset, chunk.text_hash),
                    )
                await db.commit()
            except Exception:
                await db.rollback()
                raise
        return (
            Source(
                id=id, content_hash=content_hash, version=version,
                source_type=source_type, origin_uri=origin_uri, scope=scope,
                ingested_at=ingested_at, recorded_at=recorded_at,
                valid_from=valid_from, valid_to=valid_to,
            ),
            True,
        )

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
