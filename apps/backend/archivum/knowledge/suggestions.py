"""Persistence for agent-proposed memory edits awaiting human review."""

from __future__ import annotations

import json
from typing import Any, Literal
from uuid import uuid4

import aiosqlite
from pydantic import BaseModel, Field


SuggestionStatus = Literal[
    "pending",
    "accepted",
    "edited",
    "rejected",
    "merged",
    "replaced",
    "kept",
    "retired",
    "scope_changed",
    "visibility_changed",
    "expired",
]
SuggestionAction = Literal[
    "accept",
    "edit",
    "reject",
    "merge",
    "replace",
    "keep_both",
    "retire",
    "change_scope",
    "change_visibility",
    "expire",
]

ACTION_TO_STATUS: dict[SuggestionAction, SuggestionStatus] = {
    "accept": "accepted",
    "edit": "edited",
    "reject": "rejected",
    "merge": "merged",
    "replace": "replaced",
    "keep_both": "kept",
    "retire": "retired",
    "change_scope": "scope_changed",
    "change_visibility": "visibility_changed",
    "expire": "expired",
}

_STATUS_SQL = (
    "'pending', 'accepted', 'edited', 'rejected', 'merged', 'replaced', "
    "'kept', 'retired', 'scope_changed', 'visibility_changed', 'expired'"
)


class MemorySuggestion(BaseModel):
    id: str
    target_id: str
    suggestion_type: str
    proposed_markdown: str
    proposed_objects: list[Any]
    citations: list[Any]
    proposed_scopes: list[str] = Field(default_factory=list)
    scores: dict[str, float] = Field(default_factory=dict)
    duplicates: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    retention_tier: str = "candidate"
    agent_visibility: str = "review_required"
    rationale: str = ""
    estimated_durability: str = ""
    expires_at: str | None = None
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
            proposed_scopes   TEXT NOT NULL DEFAULT '[]',
            scores            TEXT NOT NULL DEFAULT '{}',
            duplicates        TEXT NOT NULL DEFAULT '[]',
            conflicts         TEXT NOT NULL DEFAULT '[]',
            retention_tier    TEXT NOT NULL DEFAULT 'candidate',
            agent_visibility  TEXT NOT NULL DEFAULT 'review_required',
            rationale         TEXT NOT NULL DEFAULT '',
            estimated_durability TEXT NOT NULL DEFAULT '',
            expires_at        TEXT,
            status            TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ('pending', 'accepted', 'edited',
                                                'rejected', 'merged', 'replaced',
                                                'kept', 'retired', 'scope_changed',
                                                'visibility_changed', 'expired')),
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_memory_suggestions_target_status
            ON memory_suggestions(target_id, status);
        """
    )
    await _migrate_status_check(conn)
    await _migrate_review_card_columns(conn)
    await conn.commit()


async def _migrate_status_check(conn: aiosqlite.Connection) -> None:
    """Expand older suggestion tables whose CHECK only allowed accept/reject."""
    async with conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='memory_suggestions'"
    ) as cursor:
        row = await cursor.fetchone()
    if row is None or "scope_changed" in row["sql"]:
        return
    await conn.executescript(
        f"""
        CREATE TABLE memory_suggestions_new (
            id                TEXT PRIMARY KEY,
            target_id         TEXT NOT NULL,
            suggestion_type   TEXT NOT NULL,
            proposed_markdown TEXT NOT NULL,
            proposed_objects  TEXT NOT NULL,
            citations         TEXT NOT NULL,
            status            TEXT NOT NULL DEFAULT 'pending'
                              CHECK (status IN ({_STATUS_SQL})),
            created_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
        );

        INSERT INTO memory_suggestions_new
            (id, target_id, suggestion_type, proposed_markdown,
             proposed_objects, citations, status, created_at, updated_at)
        SELECT id, target_id, suggestion_type, proposed_markdown,
               proposed_objects, citations, status, created_at, updated_at
        FROM memory_suggestions;

        DROP TABLE memory_suggestions;
        ALTER TABLE memory_suggestions_new RENAME TO memory_suggestions;
        """
    )
    await conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_memory_suggestions_target_status
            ON memory_suggestions(target_id, status)
        """
    )
    await conn.commit()


async def _migrate_review_card_columns(conn: aiosqlite.Connection) -> None:
    async with conn.execute("PRAGMA table_info(memory_suggestions)") as cursor:
        rows = await cursor.fetchall()
    columns = {row["name"] for row in rows}
    additions = {
        "proposed_scopes": "TEXT NOT NULL DEFAULT '[]'",
        "scores": "TEXT NOT NULL DEFAULT '{}'",
        "duplicates": "TEXT NOT NULL DEFAULT '[]'",
        "conflicts": "TEXT NOT NULL DEFAULT '[]'",
        "retention_tier": "TEXT NOT NULL DEFAULT 'candidate'",
        "agent_visibility": "TEXT NOT NULL DEFAULT 'review_required'",
        "rationale": "TEXT NOT NULL DEFAULT ''",
        "estimated_durability": "TEXT NOT NULL DEFAULT ''",
        "expires_at": "TEXT",
    }
    for column, definition in additions.items():
        if column not in columns:
            await conn.execute(
                f"ALTER TABLE memory_suggestions ADD COLUMN {column} {definition}"
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
        proposed_scopes: list[str] | None = None,
        scores: dict[str, float] | None = None,
        duplicates: list[str] | None = None,
        conflicts: list[str] | None = None,
        retention_tier: str = "candidate",
        agent_visibility: str = "review_required",
        rationale: str = "",
        estimated_durability: str = "",
        expires_at: str | None = None,
    ) -> MemorySuggestion:
        suggestion = MemorySuggestion(
            id=f"suggestion:{uuid4()}",
            target_id=target_id,
            suggestion_type=suggestion_type,
            proposed_markdown=proposed_markdown,
            proposed_objects=proposed_objects,
            citations=citations,
            proposed_scopes=proposed_scopes or [],
            scores=scores or {},
            duplicates=duplicates or [],
            conflicts=conflicts or [],
            retention_tier=retention_tier,
            agent_visibility=agent_visibility,
            rationale=rationale,
            estimated_durability=estimated_durability,
            expires_at=expires_at,
            status="pending",
        )
        await self._conn.execute(
            """
            INSERT INTO memory_suggestions
                (id, target_id, suggestion_type, proposed_markdown,
                 proposed_objects, citations, proposed_scopes, scores, duplicates,
                 conflicts, retention_tier, agent_visibility, rationale,
                 estimated_durability, expires_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                suggestion.id,
                suggestion.target_id,
                suggestion.suggestion_type,
                suggestion.proposed_markdown,
                json.dumps(suggestion.proposed_objects),
                json.dumps(suggestion.citations),
                json.dumps(suggestion.proposed_scopes),
                json.dumps(suggestion.scores),
                json.dumps(suggestion.duplicates),
                json.dumps(suggestion.conflicts),
                suggestion.retention_tier,
                suggestion.agent_visibility,
                suggestion.rationale,
                suggestion.estimated_durability,
                suggestion.expires_at,
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

    async def transition_suggestion(
        self, suggestion_id: str, action: SuggestionAction
    ) -> None:
        await self._transition(suggestion_id, ACTION_TO_STATUS[action])

    async def expire_due_candidates(self, now: str) -> list[MemorySuggestion]:
        async with self._conn.execute(
            """
            SELECT id FROM memory_suggestions
            WHERE status='pending' AND expires_at IS NOT NULL AND expires_at <= ?
            ORDER BY expires_at ASC, id ASC
            """,
            (now,),
        ) as cursor:
            rows = await cursor.fetchall()
        expired: list[MemorySuggestion] = []
        for row in rows:
            await self._transition(row["id"], "expired")
            loaded = await self.get_suggestion(row["id"])
            if loaded is not None:
                expired.append(loaded)
        return expired

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
            proposed_scopes=json.loads(row["proposed_scopes"]),
            scores=json.loads(row["scores"]),
            duplicates=json.loads(row["duplicates"]),
            conflicts=json.loads(row["conflicts"]),
            retention_tier=row["retention_tier"],
            agent_visibility=row["agent_visibility"],
            rationale=row["rationale"],
            estimated_durability=row["estimated_durability"],
            expires_at=row["expires_at"],
            status=row["status"],
        )
