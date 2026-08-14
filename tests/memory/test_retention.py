from datetime import UTC, datetime

import aiosqlite
import pytest

from archivum.knowledge.suggestions import SuggestionRepository, init_suggestion_schema
from archivum.memory.registry import MemoryAssetRegistry, init_memory_schema
from archivum.memory.retention import run_retention_sweep


async def _connect():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await init_suggestion_schema(conn)
    await init_memory_schema(conn)
    return conn


async def _seed(conn, *, expires_at=None, created_days_ago=0):
    suggestion = await SuggestionRepository(conn).create_suggestion(
        target_id="wiki:default",
        suggestion_type="memory_atom",
        proposed_markdown="- candidate",
        proposed_objects=[],
        citations=[],
        expires_at=expires_at,
    )
    if created_days_ago:
        await conn.execute(
            "UPDATE memory_suggestions "
            "SET created_at=datetime('now', ?) WHERE id=?",
            (f"-{created_days_ago} days", suggestion.id),
        )
        await conn.commit()
    return suggestion


@pytest.mark.asyncio
async def test_sweep_expires_candidates_past_their_explicit_expiry():
    conn = await _connect()
    try:
        due = await _seed(conn, expires_at="2020-01-01T00:00:00+00:00")
        fresh = await _seed(conn, expires_at="2999-01-01T00:00:00+00:00")

        report = await run_retention_sweep(conn, now=datetime.now(UTC))

        repo = SuggestionRepository(conn)
        assert report.expired_due == 1
        assert (await repo.get_suggestion(due.id)).status == "expired"
        assert (await repo.get_suggestion(fresh.id)).status == "pending"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_sweep_expires_pending_candidates_older_than_the_scope_ttl():
    conn = await _connect()
    try:
        await MemoryAssetRegistry(conn).upsert_scope(
            id="person:self",
            wiki_id="default",
            scope_type="human",
            name="Self",
            retention_policy={"candidate_ttl_days": 7},
        )
        stale = await _seed(conn, created_days_ago=10)
        recent = await _seed(conn, created_days_ago=2)

        report = await run_retention_sweep(conn, now=datetime.now(UTC))

        repo = SuggestionRepository(conn)
        assert report.expired_over_ttl == 1
        assert (await repo.get_suggestion(stale.id)).status == "expired"
        assert (await repo.get_suggestion(recent.id)).status == "pending"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_sweep_uses_the_default_ttl_when_no_policy_is_configured():
    conn = await _connect()
    try:
        # The seeded person:self scope carries candidate_ttl_days=30.
        stale = await _seed(conn, created_days_ago=45)
        recent = await _seed(conn, created_days_ago=5)

        report = await run_retention_sweep(conn, now=datetime.now(UTC))

        repo = SuggestionRepository(conn)
        assert report.expired_over_ttl == 1
        assert (await repo.get_suggestion(stale.id)).status == "expired"
        assert (await repo.get_suggestion(recent.id)).status == "pending"
    finally:
        await conn.close()
