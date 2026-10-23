"""The internal graph router refuses every call unless a token is configured
and presented. An empty token must never mean "open"."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

import archivum.db.graph as graph
from archivum.api import internal_graph
from archivum.config import Settings


@pytest.fixture
def make_client(monkeypatch):
    calls: list[dict] = []

    async def fake_clear_legacy_projection(**kwargs):
        calls.append(kwargs)
        return "cleared"

    monkeypatch.setattr(graph, "_local_clear_legacy_projection", fake_clear_legacy_projection)

    def make(token: str) -> httpx.AsyncClient:
        settings = Settings(internal_graph_token=token)
        monkeypatch.setattr(internal_graph, "get_settings", lambda: settings)
        app = FastAPI()
        app.include_router(internal_graph.router)
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://owner")

    return make, calls


async def test_empty_configured_token_rejects_a_request_without_one(make_client):
    make, calls = make_client
    async with make("") as client:
        response = await client.post("/internal/graph/clear_legacy_projection", json={})
    assert response.status_code == 403
    assert calls == []


async def test_empty_configured_token_rejects_even_an_empty_header(make_client):
    make, calls = make_client
    async with make("") as client:
        response = await client.post(
            "/internal/graph/clear_legacy_projection", json={}, headers={"X-Internal-Token": ""}
        )
    assert response.status_code == 403
    assert calls == []


async def test_configured_token_rejects_a_missing_or_wrong_token(make_client):
    make, calls = make_client
    async with make("s3cret") as client:
        missing = await client.post("/internal/graph/clear_legacy_projection", json={})
        wrong = await client.post(
            "/internal/graph/clear_legacy_projection", json={}, headers={"X-Internal-Token": "nope"}
        )
    assert missing.status_code == 403
    assert wrong.status_code == 403
    assert calls == []


async def test_matching_token_succeeds(make_client):
    make, calls = make_client
    async with make("s3cret") as client:
        response = await client.post(
            "/internal/graph/clear_legacy_projection", json={}, headers={"X-Internal-Token": "s3cret"}
        )
    assert response.status_code == 200
    assert response.json() == {"result": "cleared"}
    assert calls == [{}]
