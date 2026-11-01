from pathlib import Path

import pytest
from starlette.testclient import TestClient

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings, get_settings


@pytest.fixture
async def client(tmp_path, monkeypatch):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    monkeypatch.setattr("archivum.api.capture.get_settings", lambda: settings)

    from archivum.api.capture import router
    from archivum.auth import CurrentUser, require_writer
    from fastapi import FastAPI

    app = FastAPI()
    # A real CurrentUser: the endpoint is typed for one and reads wiki_id off it.
    app.dependency_overrides[require_writer] = lambda: CurrentUser(
        username="admin", role="owner", wiki_id="default"
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=True)


def test_capture_endpoint_persists_conversation(client):
    resp = client.post("/api/sources/capture", json={
        "session_id": "s1", "interface": "claude_code_native",
        "turns": [
            {"role": "user", "text": "hi"},
            {"role": "assistant", "text": "<thinking>x</thinking> hello"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["deduplicated"] is False
    assert body["chunk_count"] == 2
    assert len(body["content_hash"]) == 64


def test_import_endpoint_rejects_unknown_extension(client, tmp_path):
    f = tmp_path / "x.unknown"
    f.write_text("whatever", encoding="utf-8")
    resp = client.post("/api/sources/capture/import", json={"path": str(f)})
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "no_importer"


def test_import_endpoint_missing_file_reports_unreadable(client):
    resp = client.post(
        "/api/sources/capture/import", json={"path": "/tmp/definitely-missing-x9.json"}
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["code"] == "unreadable_source"


def test_import_endpoint_returns_400_for_malformed_jsonl(client, tmp_path):
    bad = tmp_path / "bad.jsonl"
    bad.write_text("this is not json\n", encoding="utf-8")
    resp = client.post("/api/sources/capture/import", json={"path": str(bad)})
    assert resp.status_code == 400
    body = resp.json()
    detail = body.get("detail", {})
    assert detail.get("code") == "unparseable_source"


def test_capture_route_registered_on_app():
    from archivum.main import create_app

    paths = {r.path for r in create_app().routes}
    assert "/api/sources/capture" in paths
    assert "/api/sources/capture/import" in paths


async def test_import_endpoint_queues_every_imported_conversation(client):
    """A bulk import used to produce Sources nothing would ever distil.

    `/capture` queued; `/capture/import` did not. Importing a year of history
    therefore left a vault that looked full and recalled nothing, which is the
    worst of both: the storage cost without the memory.
    """
    fixture = (
        Path(__file__).parent.parent / "fixtures" / "capture" / "chatgpt_export.json"
    )
    resp = client.post(
        "/api/sources/capture/import", json={"path": str(fixture)}
    )
    assert resp.status_code == 200
    imported = [item["source_id"] for item in resp.json()["results"]]
    assert imported, "the fixture must import at least one conversation"

    jobs = await sqlite_mod.list_distillation_jobs("default")
    assert {job["source_id"] for job in jobs} == set(imported)
    assert all(job["status"] == "pending" for job in jobs)


async def test_capture_endpoint_dedupes_a_resent_session(client):
    """The Stop hook on a linked machine re-sends a session it has seen.

    The client skips an unchanged transcript, but it cannot be the only
    guard: a new machine, a cleared state directory, or a second client all
    re-send the same file. Dedup is keyed on (origin_uri, content_hash), so
    the same transcript lands on the Source that is already there.
    """
    body = {
        "session_id": "sess-1",
        "interface": "claude_code_hook",
        "started_at": "2026-10-01T00:00:00Z",
        "turns": [
            {"role": "user", "text": "why is the test red"},
            {"role": "assistant", "text": "the fixture is stale"},
        ],
        "origin_uri": "/Users/owner/.claude/projects/plasma/sess-1.jsonl",
    }

    first = client.post("/api/sources/capture", json=body)
    second = client.post("/api/sources/capture", json=body)

    assert first.status_code == second.status_code == 200
    assert first.json()["deduplicated"] is False
    assert second.json()["deduplicated"] is True
    assert second.json()["source_id"] == first.json()["source_id"]
    assert second.json()["version"] == first.json()["version"]

    # A grown transcript is the same origin with new content: a new version of
    # that Source, not a second one competing with it.
    grown = {**body, "turns": [*body["turns"], {"role": "user", "text": "fixed it"}]}
    third = client.post("/api/sources/capture", json=grown)
    assert third.json()["deduplicated"] is False
    assert third.json()["version"] == first.json()["version"] + 1
