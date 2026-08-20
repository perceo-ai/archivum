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


async def _seed(rows):
    for slug, title, tags in rows:
        await sqlite_mod.upsert_page(slug, title, "body", tags, "user", "default")


async def test_links_only_to_pages_that_exist(env):
    await _seed(
        [
            ("topics/retrieval/design", "Retrieval design", ["retrieval"]),
            ("topics/retrieval/chunking", "Chunking notes", []),
        ]
    )

    body = env.post(
        "/api/capture/preview",
        json={"text": "Reranking in Retrieval design is theatre past 25."},
    ).json()

    assert [link["slug"] for link in body["links"]] == ["topics/retrieval/design"]
    # Filed beside the page it links to, not into an invented folder.
    assert body["folder"] == "topics/retrieval"


async def test_tags_come_from_the_users_own_vocabulary(env):
    await _seed([("topics/a", "A", ["retrieval", "sleep"])])

    body = env.post(
        "/api/capture/preview", json={"text": "More retrieval work today."}
    ).json()
    assert body["tags"] == ["retrieval"]

    # A word the vault has never tagged is not invented into a tag.
    body = env.post(
        "/api/capture/preview", json={"text": "More kubernetes work today."}
    ).json()
    assert body["tags"] == []


async def test_kind_guesses_are_explained(env):
    await _seed([("topics/a", "A", [])])

    decision = env.post(
        "/api/capture/preview",
        json={"text": "We decided to ship the lexical pass first."},
    ).json()
    assert decision["kind"] == "decision"
    assert decision["reason"]

    source = env.post(
        "/api/capture/preview", json={"text": "https://example.com/paper.pdf"}
    ).json()
    assert source["kind"] == "source"

    thought = env.post(
        "/api/capture/preview", json={"text": "Why is rerank so slow?"}
    ).json()
    assert thought["kind"] == "thought"


async def test_empty_text_returns_a_neutral_preview(env):
    body = env.post("/api/capture/preview", json={"text": "   "}).json()
    assert body["kind"] == "thought"
    assert body["links"] == []
    assert body["folder"] == ""
