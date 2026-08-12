"""Persistence for agent-proposed memory edits awaiting human review."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel


SuggestionStatus = Literal["pending", "accepted", "rejected"]


class MemorySuggestion(BaseModel):
    id: str
    target_id: str
    suggestion_type: str
    proposed_markdown: str
    proposed_objects: list[Any]
    citations: list[Any]
    status: SuggestionStatus


async def init_suggestion_schema(conn: aiosqlite.Connection) -> None:
    """Create the review queue table on an open SQLite connection."""
    conn.row_factory = aiosqlite.Row
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memory_suggestions (
            id                TEXT PRIMARY KEY,
            target_id         TEXT NOT NULL,
            suggestion_type   TEXT NOT NULL,
            proposed_markdown TEXT NOT NULL,
            proposed_objects  TEXT NOT NULL,
            citations         TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'accepted', 'rejected')),
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_memory_suggestions_target_status
            ON memory_suggestions(target_id, status);
        """
    )
    await conn.commit()


class SuggestionRepository:
    """CRUD and review-state transitions for proposed memory edits."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def create_suggestion(
        self,
        *,
        target_id: str,
        suggestion_type: str,
        proposed_markdown: str,
        proposed_objects: list[Any],
        citations: list[Any],
    ) -> MemorySuggestion:
        suggestion = MemorySuggestion(
            id=f"suggestion:{uuid4()}",
            target_id=target_id,
            suggestion_type=suggestion_type,
            proposed_markdown=proposed_markdown,
            proposed_objects=proposed_objects,
            citations=citations,
            status="pending",
        )
        await self._conn.execute(
            """
            INSERT INTO memory_suggestions
                (id, target_id, suggestion_type, proposed_markdown,
                 proposed_objects, citations, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                suggestion.id,
                suggestion.target_id,
                suggestion.suggestion_type,
                suggestion.proposed_markdown,
                json.dumps(suggestion.proposed_objects),
                json.dumps(suggestion.citations),
                suggestion.status,
            ),
        )
        await self._conn.commit()
        return suggestion

    async def get_suggestion(self, suggestion_id: str) -> MemorySuggestion | None:
        async with self._conn.execute(
            "SELECT * FROM memory_suggestions WHERE id=?", (suggestion_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return self._row_to_suggestion(row) if row else None

    async def list_suggestions(
        self,
        *,
        target_id: str | None = None,
        target_ids: list[str] | None = None,
        target_prefixes: list[str] | None = None,
        status: SuggestionStatus | None = "pending",
    ) -> list[MemorySuggestion]:
        clauses: list[str] = []
        params: list[str] = []
        if target_id is not None:
            clauses.append("target_id=?")
            params.append(target_id)
        target_clauses: list[str] = []
        target_params: list[str] = []
        if target_ids:
            placeholders = ", ".join("?" for _ in target_ids)
            target_clauses.append(f"target_id IN ({placeholders})")
            target_params.extend(target_ids)
        if target_prefixes:
            for prefix in target_prefixes:
                target_clauses.append("target_id LIKE ?")
                target_params.append(f"{prefix}%")
        if target_clauses:
            clauses.append("(" + " OR ".join(target_clauses) + ")")
            params.extend(target_params)
        if status is not None:
            clauses.append("status=?")
            params.append(status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        async with self._conn.execute(
            f"SELECT * FROM memory_suggestions {where} "
            "ORDER BY updated_at DESC, created_at DESC, id ASC",
            params,
        ) as cursor:
            rows = await cursor.fetchall()
        return [self._row_to_suggestion(row) for row in rows]

    async def accept_suggestion(self, suggestion_id: str) -> None:
        await self._transition(suggestion_id, "accepted")

    async def reject_suggestion(self, suggestion_id: str) -> None:
        await self._transition(suggestion_id, "rejected")

    async def _transition(self, suggestion_id: str, target_status: SuggestionStatus) -> None:
        await self._conn.execute("BEGIN")
        try:
            cursor = await self._conn.execute(
                """
                UPDATE memory_suggestions
                SET status=?, updated_at=datetime('now')
                WHERE id=? AND status='pending'
                """,
                (target_status, suggestion_id),
            )
            if cursor.rowcount == 0:
                async with self._conn.execute(
                    "SELECT status FROM memory_suggestions WHERE id=?", (suggestion_id,)
                ) as status_cursor:
                    row = await status_cursor.fetchone()
                if row is None:
                    raise KeyError(f"Suggestion '{suggestion_id}' not found")
                if row["status"] != target_status:
                    raise ValueError(
                        f"Suggestion '{suggestion_id}' is already {row['status']}"
                    )
            await self._conn.commit()
        except Exception:
            await self._conn.rollback()
            raise

    @staticmethod
    def _row_to_suggestion(row: aiosqlite.Row) -> MemorySuggestion:
        return MemorySuggestion(
            id=row["id"],
            target_id=row["target_id"],
            suggestion_type=row["suggestion_type"],
            proposed_markdown=row["proposed_markdown"],
            proposed_objects=json.loads(row["proposed_objects"]),
            citations=json.loads(row["citations"]),
            status=row["status"],
        )
