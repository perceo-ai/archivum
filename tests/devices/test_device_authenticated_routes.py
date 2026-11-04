"""A linked machine can use the routes its own tooling calls.

Capture and the index-status poll both take a device key, because the caller is
a machine and not a browser. Both asked for a dependency that only accepts an
access JWT, so both answered 401 to every device in existence. The capture hook
is built to fail silently — a memory tool must never hold up a session — so
automatic capture uploaded nothing at all, from any machine, for as long as the
feature existed, while reporting success.

Verified against the deployment before this was written: `POST
/api/sources/capture` and `GET /api/repos` both returned 401 to a device key
that `POST /api/repos/upload` accepted.
"""

from __future__ import annotations

import archivum.db.sqlite as sqlite_mod
import pytest
from archivum.config import Settings, get_settings
from archivum.devices.repository import DeviceRepository
from fastapi import FastAPI
from starlette.testclient import TestClient


@pytest.fixture
async def linked(tmp_path, monkeypatch):
    """An app serving capture and repo routes, plus one real device key."""
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
        code_cache_dir=tmp_path / "code-cache",
    )
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    await sqlite_mod.init_db(settings)
    monkeypatch.setattr("archivum.api.capture.get_settings", lambda: settings)

    async with sqlite_mod.get_db() as conn:
        _, raw_key = await DeviceRepository(conn).mint("laptop", "default")

    from archivum.api.capture import router as capture_router
    from archivum.api.repos import router as repos_router

    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(capture_router)
    app.include_router(repos_router)  # carries its own /api/repos prefix
    return TestClient(app, raise_server_exceptions=True), raw_key


def _body():
    return {
        "session_id": "s-device",
        "interface": "claude_code_native",
        "started_at": "",
        "turns": [{"role": "user", "text": "why did the retry loop stall"}],
        "scope": "personal",
        "origin_uri": "/tmp/s-device.jsonl",
    }


async def test_a_device_key_can_capture_a_session(linked):
    client, key = linked

    response = client.post(
        "/api/sources/capture",
        json=_body(),
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["source_id"]
    # And it reached the queue, so it becomes memory rather than an inert row.
    jobs = await sqlite_mod.list_distillation_jobs("default")
    assert [job["source_id"] for job in jobs] == [response.json()["source_id"]]


async def test_a_device_key_can_read_its_own_repositories(linked):
    client, key = linked

    response = client.get("/api/repos", headers={"Authorization": f"Bearer {key}"})

    assert response.status_code == 200, response.text
    assert response.json() == []


async def test_an_unknown_key_is_still_refused(linked):
    client, _ = linked

    for bogus in ("amk_not_a_real_key_at_all_0000", "", "garbage"):
        headers = {"Authorization": f"Bearer {bogus}"} if bogus else {}
        assert client.post(
            "/api/sources/capture", json=_body(), headers=headers
        ).status_code in (401, 403)
        assert client.get("/api/repos", headers=headers).status_code in (401, 403)


async def test_a_device_cannot_import_a_file_off_the_server(linked, tmp_path):
    """Capture takes a device key; local-file import must not.

    `/capture/import` reads a path the caller chooses off the server's own
    disk, and the importer takes any readable transcript without asking whose
    it is. Accepting a device key — which every linked machine holds — would
    let one import server-local sessions it was never given, into its own
    wiki. A machine uploads its own transcript through `/capture`.
    """
    client, key = linked
    someone_elses = tmp_path / "private.jsonl"
    someone_elses.write_text("{}\n", encoding="utf-8")

    response = client.post(
        "/api/sources/capture/import",
        json={"path": str(someone_elses)},
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code in (401, 403), response.text
