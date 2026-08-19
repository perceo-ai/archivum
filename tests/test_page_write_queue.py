from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from archivum.config import Settings
from archivum.db import sqlite as sqlite_mod
from archivum.page_write_queue import apply_page_write


@pytest.mark.asyncio
async def test_a_graph_failure_no_longer_loses_the_page(monkeypatch, tmp_path: Path):
    """This inverts the previous invariant, deliberately.

    A graph failure used to abort the whole write, which meant a locked Kuzu
    made the vault read-only: you could not save a note because a *projection*
    was unavailable. Now the file and the row are canonical and land regardless,
    the projection is recorded as degraded, and a later reindex repairs it.
    """
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
        blob_dir=tmp_path / "blobs",
    )
    await sqlite_mod.init_db(settings)

    monkeypatch.setattr(
        "archivum.indexing.graph.upsert_page",
        AsyncMock(side_effect=RuntimeError("graph locked")),
    )

    row = await apply_page_write(
        title="Queued Page",
        content="ready",
        slug="queued-page",
        tags=[],
        authored_by="agent",
        wiki_id="default",
        settings=settings,
    )

    assert row["slug"] == "queued-page"
    assert (settings.wiki_dir / "queued-page.md").exists()
    assert await sqlite_mod.get_page("queued-page", "default") is not None


@pytest.mark.asyncio
async def test_the_written_file_carries_its_own_metadata(tmp_path: Path):
    """Otherwise the title lives only in SQLite, and a later hand-edit would
    rename the page out from under you."""
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
        blob_dir=tmp_path / "blobs",
    )
    await sqlite_mod.init_db(settings)

    await apply_page_write(
        title="Queued Page",
        content="ready",
        slug="queued-page",
        tags=["retrieval"],
        authored_by="agent",
        wiki_id="default",
        settings=settings,
    )

    written = (settings.wiki_dir / "queued-page.md").read_text()
    assert "title: Queued Page" in written
    assert "retrieval" in written
