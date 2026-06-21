from unittest.mock import AsyncMock

import pytest

from archivum.mcp import server


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
