"""A database created before the newer memory columns existed must be migrated.

`init_db` used to run MEMORY_SCHEMA directly, which only creates missing
tables — the columns added after the first release arrive via ALTER TABLE in
`_migrate_memory_schema`. Every test called the migrating path, so nothing
caught it until a deployed instance raised `no such column: conflict_lineage`.
"""

import aiosqlite
import pytest

from archivum.config import Settings
from archivum.db import sqlite as sqlite_mod

# The memory_assets table as it shipped before conflict lineage and review
# bookkeeping were added.
OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_assets (
    id          TEXT    NOT NULL,
    wiki_id     TEXT    NOT NULL DEFAULT 'default',
    asset_type  TEXT    NOT NULL,
    layer       TEXT    NOT NULL DEFAULT 'L1',
    name        TEXT    NOT NULL,
    owner       TEXT    NOT NULL DEFAULT 'person:self',
    scope       TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'draft',
    visibility  TEXT    NOT NULL DEFAULT 'private',
    version     INTEGER NOT NULL DEFAULT 1,
    page_slug   TEXT,
    summary     TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '[]',
    metadata    TEXT    NOT NULL DEFAULT '{}',
    citations   TEXT    NOT NULL DEFAULT '[]',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (wiki_id, id)
);
"""

NEW_COLUMNS = {
    "approved_by",
    "reviewed_at",
    "supersedes",
    "superseded_by",
    "conflict_lineage",
    "retired_at",
}


@pytest.mark.asyncio
async def test_init_db_migrates_a_pre_existing_memory_table(tmp_path):
    db_path = tmp_path / "old.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(OLD_SCHEMA)
        await conn.commit()

    settings = Settings(db_path=db_path, blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("PRAGMA table_info(memory_assets)") as cursor:
            columns = {row["name"] for row in await cursor.fetchall()}

    missing = NEW_COLUMNS - columns
    assert not missing, f"init_db left the table un-migrated: {sorted(missing)}"


@pytest.mark.asyncio
async def test_asset_counts_work_against_a_migrated_database(tmp_path):
    """The query that failed in production runs after migration."""
    db_path = tmp_path / "old.db"
    async with aiosqlite.connect(db_path) as conn:
        await conn.executescript(OLD_SCHEMA)
        await conn.commit()

    settings = Settings(db_path=db_path, blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)

    from archivum.memory.registry import MemoryAssetRegistry

    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        counts = await MemoryAssetRegistry(conn).asset_counts(wiki_id="default")

    assert counts["total"] == 0
    assert counts["disputed"] == 0
