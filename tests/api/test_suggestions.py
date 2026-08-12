from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.knowledge.suggestions import SuggestionRepository, init_suggestion_schema
from archivum.main import create_app


def _client_for_wiki(wiki_id: str) -> TestClient:
    settings = get_settings()
    token = create_access_token("owner", "owner", wiki_id, settings)
    with (
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
    ):
        app = create_app()
    client = TestClient(app, raise_server_exceptions=True)
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


async def _seed_suggestion(
    db_path,
    *,
    target_id: str,
    proposed_markdown: str = "## Suggested\n\n- [[Beta]]",
):
    async with aiosqlite.connect(str(db_path)) as conn:
        conn.row_factory = aiosqlite.Row
        await init_suggestion_schema(conn)
        return await SuggestionRepository(conn).create_suggestion(
            target_id=target_id,
            suggestion_type="append_section",
            proposed_markdown=proposed_markdown,
            proposed_objects=[],
            citations=[],
        )


def _patch_suggestion_db(monkeypatch: pytest.MonkeyPatch, db_path) -> None:
    from archivum.api import suggestions as suggestions_api

    @asynccontextmanager
    async def get_db():
        async with aiosqlite.connect(str(db_path)) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    monkeypatch.setattr(suggestions_api.sqlite, "get_db", get_db)


def test_suggestion_routes_require_auth():
    client = TestClient(create_app(), raise_server_exceptions=True)
    response = client.get("/api/suggestions")
    assert response.status_code == 401


def test_list_suggestions_returns_only_authenticated_wiki(tmp_path, monkeypatch):
    owned = asyncio.run(
        _seed_suggestion(tmp_path / "suggestions.db", target_id="page:alpha:home")
    )
    asyncio.run(
        _seed_suggestion(
            tmp_path / "suggestions.db",
            target_id="page:other:home",
            proposed_markdown="## Other wiki",
        )
    )
    _patch_suggestion_db(monkeypatch, tmp_path / "suggestions.db")

    response = _client_for_wiki("alpha").get("/api/suggestions")

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [owned.id]
    assert body[0]["target_id"] == "page:alpha:home"


def test_list_page_suggestions_uses_authenticated_wiki_scope(tmp_path, monkeypatch):
    match = asyncio.run(
        _seed_suggestion(
            tmp_path / "suggestions.db", target_id="page:alpha:notes/home"
        )
    )
    asyncio.run(
        _seed_suggestion(
            tmp_path / "suggestions.db", target_id="page:other:notes/home"
        )
    )
    _patch_suggestion_db(monkeypatch, tmp_path / "suggestions.db")

    response = _client_for_wiki("alpha").get("/api/suggestions?page_slug=notes/home")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [match.id]


def test_accept_reject_enforce_scope_and_conflicts(tmp_path, monkeypatch):
    db_path = tmp_path / "suggestions.db"
    owned = asyncio.run(_seed_suggestion(db_path, target_id="page:alpha:home"))
    other = asyncio.run(_seed_suggestion(db_path, target_id="page:other:home"))
    _patch_suggestion_db(monkeypatch, db_path)
    client = _client_for_wiki("alpha")

    accepted = client.post(f"/api/suggestions/{owned.id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"

    conflict = client.post(f"/api/suggestions/{owned.id}/reject")
    assert conflict.status_code == 409

    hidden = client.post(f"/api/suggestions/{other.id}/accept")
    assert hidden.status_code == 404


def test_create_suggestion_rejects_cross_wiki_targets(tmp_path, monkeypatch):
    db_path = tmp_path / "suggestions.db"
    asyncio.run(_seed_suggestion(db_path, target_id="page:alpha:seed"))
    _patch_suggestion_db(monkeypatch, db_path)

    response = _client_for_wiki("alpha").post(
        "/api/suggestions",
        json={
            "target_id": "page:other:home",
            "suggestion_type": "append_section",
            "proposed_markdown": "## Cross wiki",
            "proposed_objects": [],
            "citations": [],
        },
    )

    assert response.status_code == 403
