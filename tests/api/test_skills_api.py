"""Skills that follow you to every machine.

A skill is a repeatable procedure you would otherwise re-explain each session.
They live in `~/.claude/skills/` on one laptop, which is the same problem
`CLAUDE.md` has and the reason this product exists: per-machine, tied to a
checkout, invisible from anywhere else.

Stored as ordinary vault pages under `skills/`, so they are markdown on disk,
editable in the browser, and versioned like everything else. Nothing here
invents a second store.
"""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest
from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.devices.schema import init_devices_schema


@pytest.fixture
def client(tmp_path):
    db_path = tmp_path / "skills.db"

    async def _prepare():
        async with aiosqlite.connect(db_path) as conn:
            await init_devices_schema(conn)

    asyncio.run(_prepare())

    @contextlib.asynccontextmanager
    async def fake_get_db():
        async with aiosqlite.connect(db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    settings = get_settings()
    token = create_access_token("owner", "owner", "default", settings)

    stored: dict[str, dict] = {}
    clock = {"n": 0}

    async def fake_write(*, name, content, wiki_id):
        # A real page write moves updated_at; a fake that pins it would make
        # the conflict check untestable.
        clock["n"] += 1
        # Shaped like a real page row, because the route reads `updated_at`
        # off it — a fake that omits a field the code uses tests nothing.
        stored[name] = {
            "slug": f"skills/{name}",
            "title": name,
            "content": content,
            "wiki_id": wiki_id,
            "updated_at": f"2026-09-17T00:00:{clock['n']:02d}Z",
        }
        return stored[name]

    async def fake_list(*, wiki_id):
        return [
            {"name": n, "updated_at": stored[n]["updated_at"]} for n in sorted(stored)
        ]

    async def fake_read(name, *, wiki_id):
        return stored.get(name)

    with (
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
        patch("archivum.api.devices.sqlite.get_db", new=fake_get_db),
        patch("archivum.api.skills.write_skill", new=fake_write),
        patch("archivum.api.skills.list_skills", new=fake_list),
        patch("archivum.api.skills.read_skill", new=fake_read),
    ):
        from archivum.main import create_app

        c = TestClient(create_app(), base_url="http://localhost")
        c.cookies.set("access_token", token)
        c.cookies.set("csrf_token", "csrf-value")
        c.headers.update({"X-CSRF-Token": "csrf-value"})
        yield c


def _device_key(client) -> str:
    """Link a machine the way one really links, then use its key."""
    from archivum.devices.provisioning import PROVISION_PREFIX
    from archivum.devices.pairing import decode_pairing_token

    token = client.post("/api/mcp/provisioning-tokens", json={}).json()["token"]
    _base, secret = decode_pairing_token(token, prefix=PROVISION_PREFIX)
    return client.post(
        "/api/mcp/pairing/provision",
        json={"secret": secret, "device_name": "laptop"},
    ).json()["key"]


def test_a_machine_can_push_a_skill(client):
    key = _device_key(client)

    response = client.post(
        "/api/skills",
        json={"name": "deploy-runbook", "content": "# Deploy\n\nSteps.\n"},
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "deploy-runbook"


def test_another_machine_can_pull_what_the_first_pushed(client):
    """The whole point: written once, available everywhere."""
    first = _device_key(client)
    client.post(
        "/api/skills",
        json={"name": "deploy-runbook", "content": "# Deploy\n\nSteps.\n"},
        headers={"Authorization": f"Bearer {first}"},
    )

    second = _device_key(client)
    listed = client.get("/api/skills", headers={"Authorization": f"Bearer {second}"}).json()
    fetched = client.get(
        "/api/skills/deploy-runbook", headers={"Authorization": f"Bearer {second}"}
    ).json()

    assert [s["name"] for s in listed["skills"]] == ["deploy-runbook"]
    assert fetched["content"] == "# Deploy\n\nSteps.\n"


def test_pushing_a_skill_needs_a_device_key(client):
    response = client.post(
        "/api/skills", json={"name": "x", "content": "y"}
    )

    assert response.status_code == 401


def test_listing_skills_needs_a_device_key(client):
    assert client.get("/api/skills").status_code == 401


def test_a_skill_name_cannot_escape_the_skills_folder(client):
    """Names become page slugs under `skills/`, so a name with a path in it
    would write anywhere in the vault."""
    key = _device_key(client)

    response = client.post(
        "/api/skills",
        json={"name": "../../etc/passwd", "content": "x"},
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 400


def test_an_unknown_skill_is_a_404_not_an_empty_body(client):
    key = _device_key(client)

    response = client.get(
        "/api/skills/never-written", headers={"Authorization": f"Bearer {key}"}
    )

    assert response.status_code == 404


def test_pushing_the_same_name_replaces_rather_than_duplicates(client):
    """Editing a skill on one machine and pushing must update, not fork."""
    key = _device_key(client)
    headers = {"Authorization": f"Bearer {key}"}
    first = client.post(
        "/api/skills", json={"name": "runbook", "content": "v1"}, headers=headers
    ).json()

    client.post(
        "/api/skills",
        json={"name": "runbook", "content": "v2", "base_updated_at": first["updated_at"]},
        headers=headers,
    )

    listed = client.get("/api/skills", headers=headers).json()["skills"]
    assert len(listed) == 1
    assert client.get("/api/skills/runbook", headers=headers).json()["content"] == "v2"


def test_a_stale_machine_cannot_silently_destroy_another_machines_edit(client):
    """Pages keep no history, so a blind overwrite is unrecoverable.

    Machine A and machine B both hold v1. B pushes v2. A, still holding v1,
    pushes its own edit — and used to win, deleting B's work with nothing left
    to restore it from.
    """
    key = _device_key(client)
    headers = {"Authorization": f"Bearer {key}"}
    v1 = client.post(
        "/api/skills", json={"name": "runbook", "content": "v1"}, headers=headers
    ).json()
    client.post(
        "/api/skills",
        json={"name": "runbook", "content": "from machine B", "base_updated_at": v1["updated_at"]},
        headers=headers,
    )

    stale = client.post(
        "/api/skills",
        json={"name": "runbook", "content": "from machine A", "base_updated_at": v1["updated_at"]},
        headers=headers,
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "skill_conflict"
    # B's edit survives.
    assert client.get("/api/skills/runbook", headers=headers).json()["content"] == "from machine B"


def test_a_first_push_needs_no_base_version(client):
    """Nothing stored means nothing to clobber."""
    key = _device_key(client)

    response = client.post(
        "/api/skills",
        json={"name": "brand-new", "content": "x"},
        headers={"Authorization": f"Bearer {key}"},
    )

    assert response.status_code == 200
