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
