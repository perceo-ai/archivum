from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.main import create_app


@pytest.fixture
def temp_settings(tmp_path):
    return Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
    )


@pytest.fixture
async def life_client(temp_settings):
    await sqlite.init_db(temp_settings)
    token = create_access_token("owner", "owner", "default", temp_settings)

    with (
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
        patch("archivum.life_os.service.qdrant.upsert_page", new=AsyncMock()),
    ):
        app = create_app()
        app.dependency_overrides[get_settings] = lambda: temp_settings
        client = TestClient(app, raise_server_exceptions=True)
        client.headers.update({"Authorization": f"Bearer {token}"})
        yield client


def test_daily_note_endpoint(life_client):
    response = life_client.post("/api/life/daily", json={"date": "2026-06-21"})
    assert response.status_code == 200
    body = response.json()
    assert body["slug"] == "daily-2026-06-21"


def test_project_endpoint(life_client):
    response = life_client.post(
        "/api/life/projects",
        json={"key": "phoenix", "name": "Phoenix", "summary": "Second brain MVP"},
    )
    assert response.status_code == 200
    assert response.json()["key"] == "phoenix"

    list_response = life_client.get("/api/life/projects")
    assert list_response.status_code == 200
    assert list_response.json()[0]["key"] == "phoenix"
