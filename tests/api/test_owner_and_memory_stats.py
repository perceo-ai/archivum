from unittest.mock import AsyncMock, patch

import pytest_asyncio
from fastapi.testclient import TestClient

import archivum.db.sqlite as sqlite_mod
from archivum.auth import CurrentUser, get_current_user, require_owner, require_writer
from archivum.config import Settings, get_settings
from archivum.main import create_app
from archivum.knowledge.personal_root import SELF_SCOPE


@pytest_asyncio.fixture
async def env(tmp_path):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        owner_username="admin",
    )
    await sqlite_mod.init_db(settings)

    with (
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
    ):
        app = create_app()

    owner = CurrentUser(username="owner", role="owner", wiki_id="default")
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[require_writer] = lambda: owner
    app.dependency_overrides[require_owner] = lambda: owner
    app.dependency_overrides[get_settings] = lambda: settings

    yield TestClient(app, raise_server_exceptions=True)


async def test_me_falls_back_to_owner_username(env):
    res = env.get("/api/me")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == "admin"
    assert body["initials"] == "AD"
    assert body["scope_id"] == SELF_SCOPE
    assert body["role"] == "owner"


async def test_me_uses_self_scope_name_once_set(env):
    created = env.post(
        "/api/memory/scopes",
        json={"id": SELF_SCOPE, "scope_type": "human", "name": "Pranav Kannepalli"},
    )
    assert created.status_code == 201, created.text

    await sqlite_mod.upsert_page("notes/a", "A", "body", [], "user", "default")

    body = env.get("/api/me").json()
    assert body["name"] == "Pranav Kannepalli"
    assert body["initials"] == "PK"
    assert body["since"]
    assert body["pages"] == 1


async def test_memory_stats_counts_review_outcomes(env):
    await sqlite_mod.upsert_page("notes/a", "A", "body", [], "user", "default")

    kept = env.post(
        "/api/suggestions",
        json={
            "page_slug": "notes/a",
            "suggestion_type": "edit",
            "proposed_markdown": "Keep me.",
        },
    ).json()
    env.post(
        "/api/suggestions",
        json={
            "page_slug": "notes/a",
            "suggestion_type": "edit",
            "proposed_markdown": "Still pending.",
        },
    )
    accepted = env.post(f"/api/suggestions/{kept['id']}/accept")
    assert accepted.status_code == 200, accepted.text

    stats = env.get("/api/memory/stats").json()
    assert stats["suggestions_total"] == 2
    assert stats["suggestions_pending"] == 1
    assert stats["suggestions_kept"] == 1
    # Nothing was rejected, so the dropped bucket stays empty rather than
    # absorbing the pending one.
    assert stats["suggestions_dropped"] == 0


async def test_memory_stats_reports_asset_state(env):
    payload = {
        "id": "memory:wiki:notes",
        "asset_type": "wiki",
        "layer": "L1",
        "name": "Notes",
        "summary": "Editable notes",
        "body": "# Notes",
        "status": "draft",
    }
    assert env.post("/api/memory/assets", json=payload).status_code == 201

    stats = env.get("/api/memory/stats").json()
    assert stats["assets_total"] == 1
    assert stats["assets_draft"] == 1
    assert stats["assets_active"] == 0
    assert stats["assets_by_layer"]["L1"] == 1
    assert stats["assets_disputed"] == 0


async def test_assets_filter_by_page_slug(env):
    env.post(
        "/api/memory/assets",
        json={
            "id": "memory:wiki:a",
            "asset_type": "wiki",
            "layer": "L1",
            "name": "A",
            "page_slug": "notes/a",
        },
    )
    env.post(
        "/api/memory/assets",
        json={
            "id": "memory:wiki:b",
            "asset_type": "wiki",
            "layer": "L1",
            "name": "B",
            "page_slug": "notes/b",
        },
    )

    only_a = env.get("/api/memory/assets?page_slug=notes/a").json()
    assert [asset["id"] for asset in only_a] == ["memory:wiki:a"]


async def test_graph_marks_demo_fallback(env):
    # Kuzu is unavailable in tests, so the endpoint serves the demo fixture. The
    # response must say so — an unlabelled fake graph is indistinguishable from
    # the user's real one.
    body = env.get("/api/graph").json()
    assert body["source"] == "demo"
    assert body["nodes"]


async def test_me_reports_whether_setup_has_happened(env):
    before = env.get("/api/me").json()
    assert before["needs_setup"] is True

    env.post(
        "/api/memory/scopes",
        json={"id": SELF_SCOPE, "scope_type": "human", "name": "Pranav Kannepalli"},
    )

    after = env.get("/api/me").json()
    assert after["needs_setup"] is False
