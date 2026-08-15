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
    """Expire due and over-TTL pending candidates in one pass.

    TTLs are per-wiki: each wiki with a configured `person:self` retention
    policy gets its own horizon; candidates from unconfigured wikis fall back
    to the default TTL.
    """
    moment = (now or datetime.now(UTC)).isoformat()
    suggestions = SuggestionRepository(conn)
    expired_due = await suggestions.expire_due_candidates(moment)
    ttls = await _candidate_ttls_by_wiki(conn)
    expired_over_ttl = 0
    for wiki_id, ttl_days in ttls.items():
        expired_over_ttl += len(
            await suggestions.expire_stale_candidates(
                moment, ttl_days=ttl_days, wiki_id=wiki_id
            )
        )
    expired_over_ttl += len(
        await suggestions.expire_stale_candidates(
            moment,
            ttl_days=DEFAULT_CANDIDATE_TTL_DAYS,
            exclude_wiki_ids=sorted(ttls),
        )
    )
    return RetentionReport(
        expired_due=len(expired_due), expired_over_ttl=expired_over_ttl
    )


async def _candidate_ttls_by_wiki(conn: aiosqlite.Connection) -> dict[str, int]:
    """Read each wiki's candidate TTL; skip unset or unparseable policies."""
    async with conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_scopes'"
    ) as cursor:
        if await cursor.fetchone() is None:
            return {}
    async with conn.execute(
        "SELECT wiki_id, retention_policy FROM memory_scopes WHERE id='person:self'"
    ) as cursor:
        rows = await cursor.fetchall()
    ttls: dict[str, int] = {}
    for row in rows:
        try:
            policy = json.loads(row["retention_policy"])
            ttl = int(policy.get("candidate_ttl_days", DEFAULT_CANDIDATE_TTL_DAYS))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        ttls[row["wiki_id"]] = ttl if ttl > 0 else DEFAULT_CANDIDATE_TTL_DAYS
    return ttls


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
