"""A database written before `sources.wiki_id` existed has to keep working.

This is the shape of a bug that already reached production once: the schema
script only creates missing *tables*, so a column added later never lands on an
existing database, and every query naming it fails at runtime while the whole
test suite stays green.
"""

from __future__ import annotations

import aiosqlite
import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings
from archivum.store.repository import SourceStore
from archivum.store.schema import init_evidence_schema

# The sources table as it was before the tenancy column.
_OLD_SOURCES = """
CREATE TABLE sources (
    id            TEXT    PRIMARY KEY,
    content_hash  TEXT    NOT NULL,
    version       INTEGER NOT NULL,
    source_type   TEXT    NOT NULL,
    origin_uri    TEXT    NOT NULL,
    scope         TEXT    NOT NULL DEFAULT 'personal',
    ingested_at   TEXT    NOT NULL,
    recorded_at   TEXT    NOT NULL,
    valid_from    TEXT    NOT NULL,
    valid_to      TEXT,
    UNIQUE(origin_uri, version)
);
"""


@pytest.mark.asyncio
async def test_wiki_id_is_added_to_an_existing_database(tmp_path):
    db_path = tmp_path / "archivum.db"

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(_OLD_SOURCES)
        await db.execute(
            "INSERT INTO sources "
            "(id, content_hash, version, source_type, origin_uri, scope, "
            " ingested_at, recorded_at, valid_from, valid_to) "
            "VALUES ('old', 'h', 1, 'document', 'file:///old.txt', 'personal',"
            " 't', 't', 't', NULL)"
        )
        await db.commit()

    settings = Settings(db_path=db_path)
    await sqlite_mod.init_db(settings)

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA table_info(sources)") as cur:
            columns = {row[1] for row in await cur.fetchall()}
    assert "wiki_id" in columns

    # A row that predates tenancy belongs to the only vault that could have
    # written it, so it must still be visible rather than silently orphaned.
    listed = await SourceStore().list_sources(wiki_id="default")
    assert [s.id for s in listed] == ["old"]
    assert listed[0].wiki_id == "default"


@pytest.mark.asyncio
async def test_migration_is_idempotent(tmp_path):
    db_path = tmp_path / "archivum.db"
    settings = Settings(db_path=db_path)
    await sqlite_mod.init_db(settings)

    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await init_evidence_schema(db)
        await init_evidence_schema(db)
        async with db.execute("PRAGMA table_info(sources)") as cur:
            names = [row[1] for row in await cur.fetchall()]
    assert names.count("wiki_id") == 1
