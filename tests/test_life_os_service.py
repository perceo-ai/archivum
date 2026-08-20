"""Daily and project notes are pages, and only pages.

They used to be written twice — once as a page, once into a parallel life_*
table — so the same nouns had two models that could disagree, and only the
weaker one had an API. The tables are gone; these assert the page behaviour
that survived.
"""

import pytest

from archivum.config import Settings
from archivum.db import sqlite
from archivum.life_os.service import ensure_daily_note, register_project


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
        blob_dir=tmp_path / "blobs",
    )
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("archivum.life_os.service.get_settings", lambda: settings)
    return settings


@pytest.mark.asyncio
async def test_daily_note_lands_in_the_daily_folder(temp_settings):
    await sqlite.init_db(temp_settings)

    page = await ensure_daily_note("2026-06-21", wiki_id="default")

    # The folder is what gives it a kind in /api/entries, so it matters.
    assert page["slug"] == "daily/2026-06-21"
    assert "type: daily" in page["content"]
    assert "## Log" in page["content"]
    # And it exists on disk, because the file is the canonical thing.
    assert (temp_settings.wiki_dir / "daily/2026-06-21.md").exists()


@pytest.mark.asyncio
async def test_asking_twice_returns_the_same_note(temp_settings):
    """Otherwise opening today twice would overwrite what you wrote this morning."""
    await sqlite.init_db(temp_settings)

    first = await ensure_daily_note("2026-06-21", wiki_id="default")
    path = temp_settings.wiki_dir / "daily/2026-06-21.md"
    path.write_text(first["content"] + "\n\nsomething I wrote\n", encoding="utf-8")

    second = await ensure_daily_note("2026-06-21", wiki_id="default")

    assert second["slug"] == first["slug"]
    assert "something I wrote" in path.read_text()


@pytest.mark.asyncio
async def test_a_project_is_just_its_page(temp_settings):
    await sqlite.init_db(temp_settings)

    project = await register_project(
        key="phoenix", name="Phoenix", summary="Second-brain MVP", wiki_id="default"
    )

    assert project["slug"] == "projects/phoenix"
    assert "type: project" in project["content"]
    assert await sqlite.get_page("projects/phoenix", "default") is not None
