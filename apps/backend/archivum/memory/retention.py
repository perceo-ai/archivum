"""Background retention sweep so candidate expiry is not a manual chore.

The strategy's retention engine starts here: stale review candidates expire
automatically, honouring the `candidate_ttl_days` retention policy configured
on the owner's memory scope. Promotion state is never touched — accepted
memory persists with its lifecycle history.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

from archivum.config import Settings
from archivum.db import sqlite
from archivum.knowledge.suggestions import SuggestionRepository

logger = logging.getLogger(__name__)

DEFAULT_CANDIDATE_TTL_DAYS = 30


@dataclass(frozen=True)
class RetentionReport:
    expired_due: int
    expired_over_ttl: int

    @property
    def total(self) -> int:
        return self.expired_due + self.expired_over_ttl


async def run_retention_sweep(
    conn: aiosqlite.Connection, *, now: datetime | None = None
) -> RetentionReport:
    """Expire due and over-TTL pending candidates in one pass."""
    moment = (now or datetime.now(UTC)).isoformat()
    suggestions = SuggestionRepository(conn)
    expired_due = await suggestions.expire_due_candidates(moment)
    ttl_days = await _candidate_ttl_days(conn)
    expired_over_ttl = await suggestions.expire_stale_candidates(
        moment, ttl_days=ttl_days
    )
    return RetentionReport(
        expired_due=len(expired_due), expired_over_ttl=len(expired_over_ttl)
    )


async def _candidate_ttl_days(conn: aiosqlite.Connection) -> int:
    """Read the owner's candidate TTL; fall back when unset or unparseable."""
    async with conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_scopes'"
    ) as cursor:
        if await cursor.fetchone() is None:
            return DEFAULT_CANDIDATE_TTL_DAYS
    async with conn.execute(
        "SELECT retention_policy FROM memory_scopes WHERE id='person:self' LIMIT 1"
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return DEFAULT_CANDIDATE_TTL_DAYS
    try:
        policy = json.loads(row["retention_policy"])
        ttl = int(policy.get("candidate_ttl_days", DEFAULT_CANDIDATE_TTL_DAYS))
    except (ValueError, TypeError, json.JSONDecodeError):
        return DEFAULT_CANDIDATE_TTL_DAYS
    return ttl if ttl > 0 else DEFAULT_CANDIDATE_TTL_DAYS


async def run_retention_worker(settings: Settings) -> None:
    """Periodically sweep retention until the app shuts down."""
    interval = max(settings.retention_sweep_interval_seconds, 60)
    while True:
        try:
            async with sqlite.get_db() as conn:
                report = await run_retention_sweep(conn)
            if report.total:
                logger.info(
                    "Retention sweep expired candidates",
                    extra={
                        "expired_due": report.expired_due,
                        "expired_over_ttl": report.expired_over_ttl,
                    },
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Retention sweep failed")
        await asyncio.sleep(interval)
