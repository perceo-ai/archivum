from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from archivum.config import Settings
from archivum.page_write_queue import apply_page_write


@pytest.mark.asyncio
async def test_apply_page_write_does_not_commit_sqlite_when_graph_fails(monkeypatch, tmp_path: Path):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
    )

    upsert_vector = AsyncMock()
    upsert_graph = AsyncMock(side_effect=RuntimeError("graph locked"))
    upsert_page = AsyncMock()
    get_page = AsyncMock()

    monkeypatch.setattr("archivum.page_write_queue.qdrant.upsert_page", upsert_vector)
    monkeypatch.setattr("archivum.page_write_queue.graph.upsert_page", upsert_graph)
    monkeypatch.setattr("archivum.page_write_queue.sqlite.upsert_page", upsert_page)
    monkeypatch.setattr("archivum.page_write_queue.sqlite.get_page", get_page)

    with pytest.raises(RuntimeError, match="graph locked"):
        await apply_page_write(
            title="Queued Page",
            content="ready",
            slug="queued-page",
            tags=[],
            authored_by="agent",
            wiki_id="default",
            settings=settings,
        )

    upsert_vector.assert_awaited_once()
    upsert_graph.assert_awaited_once()
    upsert_page.assert_not_awaited()
    get_page.assert_not_awaited()
    assert not (settings.wiki_dir / "queued-page.md").exists()
