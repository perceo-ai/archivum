from unittest.mock import AsyncMock, patch

import pytest

from archivum.config import Settings
from archivum.db import sqlite
from archivum.life_os.service import ensure_daily_note, register_project


@pytest.fixture
def temp_settings(tmp_path):
    return Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
    )


@pytest.mark.asyncio
async def test_ensure_daily_note_creates_portable_markdown(temp_settings):
    await sqlite.init_db(temp_settings)

    with patch("archivum.life_os.service.qdrant.upsert_page", new=AsyncMock()):
        page = await ensure_daily_note("2026-06-21", wiki_id="default")

    assert page["slug"] == "daily-2026-06-21"
    assert "type: daily" in page["content"]
    assert "## Log" in page["content"]
    assert "## Tasks" in page["content"]


@pytest.mark.asyncio
async def test_register_project_creates_project_page_and_row(temp_settings):
    await sqlite.init_db(temp_settings)

    with patch("archivum.life_os.service.qdrant.upsert_page", new=AsyncMock()):
        project = await register_project(
            key="phoenix",
            name="Phoenix",
            summary="Second-brain MVP",
            wiki_id="default",
        )

    page = await sqlite.get_page("project-phoenix", "default")
    projects = await sqlite.list_life_projects("default")

    assert project["page_slug"] == "project-phoenix"
    assert page is not None
    assert "type: project" in page["content"]
    assert projects[0]["key"] == "phoenix"
