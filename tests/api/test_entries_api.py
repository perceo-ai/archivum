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


async def test_kind_comes_from_folder_then_tag(env):
    await sqlite_mod.upsert_page("people/dana", "Dana R.", "body", [], "user", "default")
    await sqlite_mod.upsert_page("decisions/ship", "Ship it", "body", [], "user", "default")
    await sqlite_mod.upsert_page("topics/retrieval", "Retrieval", "body", [], "user", "default")
    # An explicit tag beats the folder it happens to sit in.
    await sqlite_mod.upsert_page(
        "topics/idea", "An idea", "body", ["type/thought"], "user", "default"
    )

    body = env.get("/api/entries").json()
    by_slug = {entry["slug"]: entry for entry in body["entries"]}

    assert by_slug["people/dana"]["kind"] == "person"
    assert by_slug["decisions/ship"]["kind"] == "decision"
    assert by_slug["topics/retrieval"]["kind"] == "note"
    assert by_slug["topics/idea"]["kind"] == "thought"


async def test_numeric_folder_prefixes_are_tolerated(env):
    await sqlite_mod.upsert_page("40 people/sam", "Sam K.", "body", [], "user", "default")
    body = env.get("/api/entries").json()
    assert body["entries"][0]["kind"] == "person"


async def test_counts_cover_the_whole_vault_not_the_filter(env):
    await sqlite_mod.upsert_page("people/dana", "Dana", "body", [], "user", "default")
    await sqlite_mod.upsert_page("topics/a", "A", "body", [], "user", "default")
    await sqlite_mod.upsert_page("topics/b", "B", "body", [], "user", "default")

    body = env.get("/api/entries?kind=person").json()
    assert [entry["slug"] for entry in body["entries"]] == ["people/dana"]
    # Facet chips show vault-wide counts even while a filter is applied.
    assert body["counts"] == {"person": 1, "note": 2}
    assert body["total"] == 3


async def test_needs_review_reflects_pending_suggestions(env):
    await sqlite_mod.upsert_page("topics/a", "A", "body", [], "user", "default")
    await sqlite_mod.upsert_page("topics/b", "B", "body", [], "user", "default")
    created = env.post(
        "/api/suggestions",
        json={
            "page_slug": "topics/a",
            "suggestion_type": "edit",
            "proposed_markdown": "Change something.",
        },
    )
    assert created.status_code == 201, created.text

    body = env.get("/api/entries?needs_review=true").json()
    assert [entry["slug"] for entry in body["entries"]] == ["topics/a"]

    everything = env.get("/api/entries").json()
    flags = {entry["slug"]: entry["needs_review"] for entry in everything["entries"]}
    assert flags == {"topics/a": True, "topics/b": False}


async def test_agent_authored_pages_are_marked(env):
    await sqlite_mod.upsert_page("topics/a", "A", "body", [], "agent", "default")
    body = env.get("/api/entries").json()
    assert body["entries"][0]["actor"] == "agent"
