from unittest.mock import AsyncMock, patch

import pytest

from archivum.config import Settings
from archivum.db import sqlite
from archivum.mcp import server


@pytest.fixture
def temp_settings(tmp_path):
    return Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
    )


@pytest.mark.asyncio
async def test_mcp_life_os_tools(temp_settings, monkeypatch):
    monkeypatch.setattr(server, "settings", temp_settings)
    await sqlite.init_db(temp_settings)

    with patch("archivum.life_os.service.qdrant.upsert_page", new=AsyncMock()):
        daily = await server.life_daily_note("2026-06-21")
        project = await server.life_register_project("phoenix", "Phoenix", "MVP")
        task = await server.life_create_task("Wire Life OS MCP", project_key="phoenix")

    assert daily["slug"] == "daily-2026-06-21"
    assert project["key"] == "phoenix"
    assert task["project_key"] == "phoenix"


@pytest.mark.asyncio
async def test_lint_wiki_reports_broken_links_and_orphans(monkeypatch):
    monkeypatch.setattr(
        server.sqlite,
        "list_pages",
        AsyncMock(
            return_value=[
                {"slug": "alpha", "content": "See [[beta]] and [[missing]]."},
                {"slug": "beta", "content": "Linked page."},
                {"slug": "orphan", "content": "No links here."},
            ]
        ),
    )

    result = await server.lint_wiki("default")

    assert result["broken_wikilinks"] == [
        {"type": "broken_wikilink", "page": "alpha", "target": "missing"}
    ]
    assert result["orphan_pages"] == ["orphan"]


@pytest.mark.asyncio
async def test_lint_wiki_reports_contradictions(monkeypatch):
    monkeypatch.setattr(
        server.sqlite,
        "list_pages",
        AsyncMock(
            return_value=[
                {"slug": "ops-a", "content": "Public wiki is enabled."},
                {"slug": "ops-b", "content": "Public wiki is disabled."},
            ]
        ),
    )

    result = await server.lint_wiki("default")

    assert result["contradictory_claims"] == [
        {
            "type": "contradictory_claim",
            "subject": "public wiki",
            "pages": ["ops-a", "ops-b"],
            "claims": ["enabled", "disabled"],
        }
    ]


@pytest.mark.asyncio
async def test_dispatch_command_returns_help_without_touching_storage():
    result = await server.dispatch_command("help")

    assert result["ok"] is True
    assert result["command"] == "help"
    assert "search <query>" in result["actions"]


@pytest.mark.asyncio
async def test_dispatch_command_rejects_invalid_write_payload():
    result = await server.dispatch_command("write title without separator")

    assert result["error"] == "invalid_payload"


@pytest.mark.asyncio
async def test_query_returns_missing_key_for_openrouter(monkeypatch):
    monkeypatch.setattr(server.settings, "llm_synthesis_provider", "openrouter")
    monkeypatch.setattr(server.settings, "openrouter_api_key", "")

    result = await server.query("What changed?", wiki_id="default")

    assert result == {
        "error": "missing_api_key",
        "detail": "OPENROUTER_API_KEY not configured",
    }


@pytest.mark.asyncio
async def test_write_page_queues_backend_job_instead_of_direct_indexing(monkeypatch):
    monkeypatch.setattr(server.sqlite, "enqueue_page_write_job", AsyncMock(return_value=17))
    monkeypatch.setattr(
        server.page_write_queue,
        "wait_for_page_write_job",
        AsyncMock(
            return_value={
                "id": 17,
                "status": "done",
                "result_slug": "queued-page",
                "error": None,
            }
        ),
    )
    monkeypatch.setattr(
        server,
        "get_page",
        AsyncMock(return_value={"slug": "queued-page", "title": "Queued Page", "content": "ready"}),
    )
    upsert_page = AsyncMock()
    upsert_graph = AsyncMock()
    monkeypatch.setattr(server.qdrant, "upsert_page", upsert_page)
    monkeypatch.setattr(server.graph, "upsert_page", upsert_graph)

    result = await server.write_page("Queued Page", "ready", wiki_id="default")

    server.sqlite.enqueue_page_write_job.assert_awaited_once()
    server.page_write_queue.wait_for_page_write_job.assert_awaited_once_with(17, wiki_id="default")
    upsert_page.assert_not_awaited()
    upsert_graph.assert_not_awaited()
    assert result["slug"] == "queued-page"
