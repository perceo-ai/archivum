from unittest.mock import AsyncMock, patch

import pytest_asyncio
from fastapi.testclient import TestClient

import archivum.db.sqlite as sqlite_mod
from archivum.auth import CurrentUser, get_current_user, require_writer
from archivum.config import Settings, get_settings
from archivum.main import create_app


@pytest_asyncio.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
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
    app.dependency_overrides[get_settings] = lambda: settings

    yield TestClient(app, raise_server_exceptions=True)


async def test_activity_merges_pages_and_suggestions(env):
    client = env
    await sqlite_mod.upsert_page(
        "notes/retrieval", "Retrieval design", "# Retrieval", [], "user", "default"
    )
    await sqlite_mod.upsert_page(
        "notes/agent-note", "Agent note", "# Written by an agent", [], "agent", "default"
    )

    created = client.post(
        "/api/suggestions",
        json={
            "page_slug": "notes/retrieval",
            "suggestion_type": "edit",
            "proposed_markdown": "Rerank the top 25 candidates.",
            "rationale": "The eval shows no gain past 25.",
        },
    )
    assert created.status_code == 201, created.text

    res = client.get("/api/activity")
    assert res.status_code == 200, res.text
    feed = res.json()

    kinds = {item["kind"] for item in feed["items"]}
    assert "page_created" in kinds
    assert "suggestion" in kinds
    assert feed["pending_review"] == 1

    # Newest first, and every item carries a usable timestamp.
    times = [item["at"] for item in feed["items"]]
    assert all(times)
    assert times == sorted(times, reverse=True)

    by_slug = {item["slug"]: item for item in feed["items"] if item["kind"].startswith("page")}
    assert by_slug["notes/agent-note"]["actor"] == "agent"
    assert by_slug["notes/retrieval"]["actor"] == "you"

    suggestion = next(item for item in feed["items"] if item["kind"] == "suggestion")
    assert suggestion["needs_review"] is True
    assert suggestion["actor"] == "agent"
    assert suggestion["slug"] == "notes/retrieval"


async def test_activity_respects_limit_and_cursor(env):
    client = env
    for i in range(5):
        await sqlite_mod.upsert_page(
            f"notes/page-{i}", f"Page {i}", "body", [], "user", "default"
        )

    first = client.get("/api/activity?limit=2").json()
    assert len(first["items"]) == 2
    assert first["next_before"]

    second = client.get(f"/api/activity?limit=2&before={first['next_before']}").json()
    assert len(second["items"]) <= 2
    first_ids = {item["id"] for item in first["items"]}
    assert not (first_ids & {item["id"] for item in second["items"]})


async def test_suggestions_expose_timestamps(env):
    client = env
    await sqlite_mod.upsert_page("notes/a", "A", "body", [], "user", "default")
    created = client.post(
        "/api/suggestions",
        json={
            "page_slug": "notes/a",
            "suggestion_type": "edit",
            "proposed_markdown": "Something.",
        },
    ).json()

    # Written by SQLite defaults, so they must survive the round trip rather
    # than coming back as the empty-string model default.
    assert created["created_at"]
    assert created["updated_at"]

    listed = client.get("/api/suggestions").json()
    assert listed[0]["created_at"] == created["created_at"]
