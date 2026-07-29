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
