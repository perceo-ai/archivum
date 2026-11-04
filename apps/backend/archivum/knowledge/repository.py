"""SQLite persistence for provenance-aware knowledge objects and relationships."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from typing import Any

import aiosqlite

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.store.schema import init_evidence_schema


async def init_knowledge_schema(conn: aiosqlite.Connection) -> None:
    """Create the knowledge tables on an open SQLite connection."""
    conn.row_factory = aiosqlite.Row
    await init_evidence_schema(conn)
    await conn.commit()


class KnowledgeRepository:
    """CRUD repository for canonical, provenance-aware knowledge records."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    @asynccontextmanager
    async def transaction(self, *, immediate: bool = False) -> AsyncIterator[None]:
        """Group writes into one commit.

        Both `upsert_object` and `upsert_relationship` commit per call by
        default, which is right for a single write and wrong for a batch: a page
        with a hundred mentions became a hundred transactions, each taking the
        one write lock while background workers waited for it.

        `immediate` is for read-modify-write. A deferred BEGIN lets two
        connections read the same row and then collide on the write, which
        SQLite reports as "database is locked" rather than waiting; BEGIN
        IMMEDIATE takes the write lock up front, so the second caller waits
        out the busy timeout and then reads what the first one wrote.
        """
        await self._conn.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        try:
            yield
        except Exception:
            await self._conn.rollback()
            raise
        await self._conn.commit()

    async def upsert_object(self, obj: KnowledgeObject, *, commit: bool = True) -> None:
        """Write one object; pass commit=False inside an open transaction."""
        if commit:
            await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                """
                INSERT INTO knowledge_objects
                    (id, kind, label, scope, confidence, extraction_method, properties)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    kind=excluded.kind,
                    label=excluded.label,
                    scope=excluded.scope,
                    confidence=excluded.confidence,
                    extraction_method=excluded.extraction_method,
                    properties=excluded.properties
                """,
                (
                    obj.id,
                    obj.kind,
                    obj.label,
                    obj.scope,
                    obj.confidence,
                    obj.extraction_method,
                    json.dumps(obj.properties),
                ),
            )
            await self._replace_citations("object", obj.id, obj.citations)
            if commit:
                await self._conn.commit()
        except Exception:
            if commit:
                await self._conn.rollback()
            raise

    async def upsert_relationship(
        self, rel: KnowledgeRelationship, *, commit: bool = True
    ) -> None:
        """Write one edge; pass commit=False inside an open transaction.

        Matches `upsert_object`. Writing a page's mentions one transaction at a
        time turned a single page index into hundreds of commits, each competing
        with the background workers for the write lock.
        """
        if commit:
            await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                """
                INSERT INTO knowledge_relationships
                    (id, src_id, dst_id, rel_type, scope, confidence, extraction_method, properties)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    src_id=excluded.src_id,
                    dst_id=excluded.dst_id,
                    rel_type=excluded.rel_type,
                    scope=excluded.scope,
                    confidence=excluded.confidence,
                    extraction_method=excluded.extraction_method,
                    properties=excluded.properties
                """,
                (
                    rel.id,
                    rel.src_id,
                    rel.dst_id,
                    rel.rel_type,
                    rel.scope,
                    rel.confidence,
                    rel.extraction_method,
                    json.dumps(rel.properties),
                ),
            )
            await self._replace_citations("relationship", rel.id, rel.citations)
            if commit:
                await self._conn.commit()
        except Exception:
            if commit:
                await self._conn.rollback()
            raise

    async def get_object(self, object_id: str) -> KnowledgeObject | None:
        async with self._conn.execute(
            "SELECT * FROM knowledge_objects WHERE id=?", (object_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return await self._row_to_object(row) if row else None

    async def list_labels(self, *, kind: str, scope: str) -> list[tuple[str, str]]:
        """Every (id, label) of one kind in one scope, uncapped.

        For callers that only match on names. `list_objects` loads citations
        row by row and stops at a limit, which is the wrong shape for "is this
        name one of ours?" — a cutoff there silently drops whatever sorts last.
        """
        async with self._conn.execute(
            "SELECT id, label FROM knowledge_objects WHERE kind=? AND scope=? ORDER BY id",
            (kind, scope),
        ) as cursor:
            return [(row[0], row[1]) for row in await cursor.fetchall()]

    async def list_objects(
        self, kind: str | None = None, scope: str | None = None, limit: int = 100
    ) -> list[KnowledgeObject]:
        clauses: list[str] = []
        params: list[str | int] = []
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind)
        if scope is not None:
            clauses.append("scope=?")
            params.append(scope)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        async with self._conn.execute(
            f"SELECT * FROM knowledge_objects{where} ORDER BY id LIMIT ?", params
        ) as cursor:
            rows = await cursor.fetchall()
        citations = await self._citations_for("object", [row["id"] for row in rows])
        return [
            await self._row_to_object(row, citations.get(row["id"], []))
            for row in rows
        ]

    async def get_relationship(self, relationship_id: str) -> KnowledgeRelationship | None:
        async with self._conn.execute(
            "SELECT * FROM knowledge_relationships WHERE id=?", (relationship_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return await self._row_to_relationship(row) if row else None

    async def list_relationships(
        self,
        node_id: str | None = None,
        scope: str | None = None,
        limit: int | None = None,
        among_ids: list[str] | None = None,
    ) -> list[KnowledgeRelationship]:
        """Relationships in a scope, optionally only those joining known nodes.

        `among_ids` is how retrieval bounds this safely. A plain `limit` takes
        the first rows by id, which is decided before anything knows what the
        query matched — so in a large scope a matched symbol could lose every
        one of its edges because unrelated ones happened to sort first. Asking
        for the edges between the nodes already loaded cannot drop a relevant
        one, because an edge to a node outside that set has nowhere to land.
        """
        if among_ids is not None:
            return await self._relationships_among(among_ids, scope)

        clauses: list[str] = []
        params: list[str | int] = []
        if node_id is not None:
            clauses.append("(src_id=? OR dst_id=?)")
            params.extend((node_id, node_id))
        if scope is not None:
            clauses.append("scope=?")
            params.append(scope)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        # This had no bound at all, and retrieval calls it per request. A repo
        # with eight thousand edges hydrated all eight thousand to return ten.
        suffix = ""
        if limit is not None:
            suffix = " LIMIT ?"
            params.append(limit)
        async with self._conn.execute(
            f"SELECT * FROM knowledge_relationships{where} ORDER BY id{suffix}", params
        ) as cursor:
            rows = await cursor.fetchall()
        return await self._hydrate_relationships(rows)

    async def _relationships_among(
        self, node_ids: list[str], scope: str | None
    ) -> list[KnowledgeRelationship]:
        """Edges whose both endpoints are in `node_ids`.

        Through a temp table rather than batched `IN (...)` lists. Batching the
        ids and requiring both endpoints inside the *same* batch drops every
        edge that happens to span two of them — with a few hundred ids per
        batch and a repository of a few thousand symbols, that is most of the
        graph, silently. A dangling edge is still excluded: one whose other end
        was never loaded has nowhere to traverse to.
        """
        if not node_ids:
            return []
        await self._conn.execute(
            "CREATE TEMP TABLE IF NOT EXISTS _relationship_scope_ids (id TEXT PRIMARY KEY)"
        )
        await self._conn.execute("DELETE FROM _relationship_scope_ids")
        await self._conn.executemany(
            "INSERT OR IGNORE INTO _relationship_scope_ids (id) VALUES (?)",
            [(node_id,) for node_id in node_ids],
        )
        sql = (
            "SELECT r.* FROM knowledge_relationships r "
            "JOIN _relationship_scope_ids a ON a.id = r.src_id "
            "JOIN _relationship_scope_ids b ON b.id = r.dst_id"
        )
        params: tuple[object, ...] = ()
        if scope is not None:
            sql += " WHERE r.scope = ?"
            params = (scope,)
        async with self._conn.execute(sql + " ORDER BY r.id", params) as cursor:
            rows = await cursor.fetchall()
        await self._conn.execute("DELETE FROM _relationship_scope_ids")
        return await self._hydrate_relationships(rows)

    async def _hydrate_relationships(
        self, rows: list[aiosqlite.Row]
    ) -> list[KnowledgeRelationship]:
        citations = await self._citations_for(
            "relationship", [row["id"] for row in rows]
        )
        return [
            await self._row_to_relationship(row, citations.get(row["id"], []))
            for row in rows
        ]

    async def delete_relationships(
        self,
        *,
        src_id: str | None = None,
        dst_id: str | None = None,
        rel_types: set[str] | None = None,
    ) -> None:
        """Delete matching relationships and their citations."""
        clauses: list[str] = []
        params: list[str] = []
        if src_id is not None:
            clauses.append("src_id=?")
            params.append(src_id)
        if dst_id is not None:
            clauses.append("dst_id=?")
            params.append(dst_id)
        if rel_types:
            placeholders = ", ".join("?" for _ in rel_types)
            clauses.append(f"rel_type IN ({placeholders})")
            params.extend(sorted(rel_types))
        if not clauses:
            raise ValueError("At least one relationship filter is required")

        where = " AND ".join(clauses)
        await self._conn.execute("BEGIN")
        try:
            async with self._conn.execute(
                f"SELECT id FROM knowledge_relationships WHERE {where}", params
            ) as cursor:
                relationship_ids = [row["id"] for row in await cursor.fetchall()]
            if relationship_ids:
                placeholders = ", ".join("?" for _ in relationship_ids)
                await self._conn.execute(
                    "DELETE FROM knowledge_citations "
                    f"WHERE knowledge_type='relationship' AND knowledge_id IN ({placeholders})",
                    relationship_ids,
                )
                await self._conn.execute(
                    f"DELETE FROM knowledge_relationships WHERE id IN ({placeholders})",
                    relationship_ids,
                )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def delete_relationship(self, relationship_id: str) -> None:
        """Delete one relationship and its citations."""
        await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                "DELETE FROM knowledge_citations WHERE knowledge_type='relationship' AND knowledge_id=?",
                (relationship_id,),
            )
            await self._conn.execute(
                "DELETE FROM knowledge_relationships WHERE id=?", (relationship_id,)
            )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def delete_object(self, object_id: str) -> None:
        """Delete an object, all incident relationships, and their citations."""
        await self._conn.execute("BEGIN")
        try:
            async with self._conn.execute(
                "SELECT id FROM knowledge_relationships WHERE src_id=? OR dst_id=?",
                (object_id, object_id),
            ) as cursor:
                relationship_ids = [row["id"] for row in await cursor.fetchall()]
            if relationship_ids:
                placeholders = ", ".join("?" for _ in relationship_ids)
                await self._conn.execute(
                    "DELETE FROM knowledge_citations "
                    f"WHERE knowledge_type='relationship' AND knowledge_id IN ({placeholders})",
                    relationship_ids,
                )
                await self._conn.execute(
                    f"DELETE FROM knowledge_relationships WHERE id IN ({placeholders})",
                    relationship_ids,
                )
            await self._conn.execute(
                "DELETE FROM knowledge_citations WHERE knowledge_type='object' AND knowledge_id=?",
                (object_id,),
            )
            await self._conn.execute("DELETE FROM knowledge_objects WHERE id=?", (object_id,))
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def delete_object_preserving_relationships(self, object_id: str) -> None:
        """Delete one object and object citations without touching incident relationships."""
        await self._conn.execute("BEGIN")
        try:
            await self._conn.execute(
                "DELETE FROM knowledge_citations WHERE knowledge_type='object' AND knowledge_id=?",
                (object_id,),
            )
            await self._conn.execute("DELETE FROM knowledge_objects WHERE id=?", (object_id,))
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    async def list_objects_from_source(
        self, source_id: str, *, scope: str | None = None, limit: int = 200
    ) -> list[KnowledgeObject]:
        """Everything whose provenance points at one source.

        Ingest already cites the source on every record it derives, so the
        source-to-page link has existed all along — it simply had no query, and
        so no way to answer "what did this PDF actually produce?".
        """
        clauses = ["c.knowledge_type='object'", "c.source_id=?"]
        params: list[Any] = [source_id]
        if scope is not None:
            clauses.append("o.scope=?")
            params.append(scope)
        params.append(max(limit, 0))

        async with self._conn.execute(
            f"""
            SELECT DISTINCT o.id
            FROM knowledge_citations AS c
            JOIN knowledge_objects AS o ON o.id = c.knowledge_id
            WHERE {' AND '.join(clauses)}
            ORDER BY o.id ASC
            LIMIT ?
            """,
            params,
        ) as cursor:
            rows = await cursor.fetchall()

        objects: list[KnowledgeObject] = []
        for row in rows:
            # Skip the source's own record: it cites itself.
            if row["id"] == source_id:
                continue
            obj = await self.get_object(row["id"])
            if obj is not None:
                objects.append(obj)
        return objects

    async def delete_records_with_only_citations_in(
        self, *, scope: str, chunk_ids: set[str]
    ) -> tuple[int, int]:
        """Delete scoped records whose complete provenance belongs to deleted chunks."""
        if not chunk_ids:
            return 0, 0

        placeholders = ", ".join("?" for _ in chunk_ids)
        deleted_chunks = sorted(chunk_ids)

        async with self._conn.execute(
            f"""
            SELECT c.knowledge_id
            FROM knowledge_citations AS c
            JOIN knowledge_relationships AS r ON r.id = c.knowledge_id
            WHERE c.knowledge_type='relationship' AND r.scope=?
            GROUP BY c.knowledge_id
            HAVING SUM(CASE WHEN c.chunk_id NOT IN ({placeholders}) THEN 1 ELSE 0 END)=0
            """,
            [scope, *deleted_chunks],
        ) as cursor:
            relationship_ids = [row[0] for row in await cursor.fetchall()]

        for relationship_id in relationship_ids:
            await self.delete_relationship(relationship_id)

        async with self._conn.execute(
            f"""
            SELECT c.knowledge_id
            FROM knowledge_citations AS c
            JOIN knowledge_objects AS o ON o.id = c.knowledge_id
            WHERE c.knowledge_type='object' AND o.scope=?
            GROUP BY c.knowledge_id
            HAVING SUM(CASE WHEN c.chunk_id NOT IN ({placeholders}) THEN 1 ELSE 0 END)=0
            """,
            [scope, *deleted_chunks],
        ) as cursor:
            object_ids = [row[0] for row in await cursor.fetchall()]

        for object_id in object_ids:
            await self.delete_object_preserving_relationships(object_id)

        return len(object_ids), len(relationship_ids)

    async def _replace_citations(
        self, knowledge_type: str, knowledge_id: str, citations: list[Citation]
    ) -> None:
        await self._conn.execute(
            "DELETE FROM knowledge_citations WHERE knowledge_type=? AND knowledge_id=?",
            (knowledge_type, knowledge_id),
        )
        await self._conn.executemany(
            """
            INSERT INTO knowledge_citations
                (knowledge_id, knowledge_type, position, source_id, chunk_id, span_start, span_end, quote)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    knowledge_id,
                    knowledge_type,
                    position,
                    citation.source_id,
                    citation.chunk_id,
                    citation.span_start,
                    citation.span_end,
                    citation.quote,
                )
                for position, citation in enumerate(citations)
            ],
        )

    async def _citations(self, knowledge_type: str, knowledge_id: str) -> list[Citation]:
        async with self._conn.execute(
            """
            SELECT source_id, chunk_id, span_start, span_end, quote
            FROM knowledge_citations
            WHERE knowledge_type=? AND knowledge_id=?
            ORDER BY position
            """,
            (knowledge_type, knowledge_id),
        ) as cursor:
            rows = await cursor.fetchall()
        return [Citation(**dict(row)) for row in rows]

    async def _citations_for(
        self, knowledge_type: str, knowledge_ids: list[str]
    ) -> dict[str, list[Citation]]:
        """Citations for many records in one pass, grouped by record id.

        Hydrating a list used to issue one citation query per row. Retrieval
        lists every object and every relationship in a scope, so answering a
        ten-node question about a repository of thirty thousand symbols cost
        tens of thousands of sequential round trips, each one a thread hop.
        """
        grouped: dict[str, list[Citation]] = {}
        # SQLITE_MAX_VARIABLE_NUMBER is 999 on older builds; stay well inside it.
        for start in range(0, len(knowledge_ids), 500):
            batch = knowledge_ids[start : start + 500]
            placeholders = ",".join("?" * len(batch))
            async with self._conn.execute(
                f"""
                SELECT knowledge_id, source_id, chunk_id, span_start, span_end, quote
                FROM knowledge_citations
                WHERE knowledge_type=? AND knowledge_id IN ({placeholders})
                ORDER BY knowledge_id, position
                """,
                (knowledge_type, *batch),
            ) as cursor:
                for row in await cursor.fetchall():
                    fields = dict(row)
                    grouped.setdefault(fields.pop("knowledge_id"), []).append(
                        Citation(**fields)
                    )
        return grouped

    async def _row_to_object(
        self, row: aiosqlite.Row, citations: list[Citation] | None = None
    ) -> KnowledgeObject:
        return KnowledgeObject(
            id=row["id"],
            kind=row["kind"],
            label=row["label"],
            scope=row["scope"],
            confidence=row["confidence"],
            extraction_method=row["extraction_method"],
            citations=(
                citations
                if citations is not None
                else await self._citations("object", row["id"])
            ),
            properties=json.loads(row["properties"]),
        )

    async def _row_to_relationship(
        self, row: aiosqlite.Row, citations: list[Citation] | None = None
    ) -> KnowledgeRelationship:
        return KnowledgeRelationship(
            id=row["id"],
            src_id=row["src_id"],
            dst_id=row["dst_id"],
            rel_type=row["rel_type"],
            scope=row["scope"],
            confidence=row["confidence"],
            extraction_method=row["extraction_method"],
            citations=(
                citations
                if citations is not None
                else await self._citations("relationship", row["id"])
            ),
            properties=json.loads(row["properties"]),
        )
