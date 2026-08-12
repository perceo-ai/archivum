import pytest

from archivum.config import Settings
from archivum.db import sqlite


@pytest.fixture
def temp_settings(tmp_path):
    return Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
    )


@pytest.mark.asyncio
async def test_create_project_and_task(temp_settings):
    await sqlite.init_db(temp_settings)

    project = await sqlite.upsert_life_project(
        wiki_id="default",
        key="phoenix",
        name="Phoenix",
        status="active",
        page_slug="project-phoenix",
        summary="Personal knowledge OS MVP",
    )
    task = await sqlite.create_life_task(
        wiki_id="default",
        title="Validate MCP server",
        status="open",
        project_key="phoenix",
        page_slug="project-phoenix",
        source="manual",
    )

    projects = await sqlite.list_life_projects("default")
    tasks = await sqlite.list_life_tasks("default", status="open")

    assert project["key"] == "phoenix"
    assert task["project_key"] == "phoenix"
    assert [p["key"] for p in projects] == ["phoenix"]
    assert [t["title"] for t in tasks] == ["Validate MCP server"]


@pytest.mark.asyncio
async def test_list_folders_creates_default_organization(temp_settings):
    await sqlite.init_db(temp_settings)

    folders = await sqlite.list_folders("default")

    assert [folder["path"] for folder in folders] == sorted(sqlite.DEFAULT_ORGANIZATION_FOLDERS)
