"""A client-role process reaches the graph through the owner, never the file.

The owner app here is only the internal graph router, served in-process
through `httpx.ASGITransport`. The owner and the client share one Python
process in this test, so which role a call runs as is carried in a
ContextVar: each asyncio task sees the settings it was started with.
"""

from __future__ import annotations

import asyncio
import contextvars
import time

import httpx
import kuzu
import pytest
from fastapi import FastAPI

import archivum.db.graph as graph
from archivum.api.internal_graph import router as internal_graph_router
from archivum.config import Settings


_role: contextvars.ContextVar[Settings] = contextvars.ContextVar("graph_test_role")


@pytest.fixture
def roles(tmp_path, monkeypatch):
    owner = Settings(kuzu_path=tmp_path / "owner-kuzu")
    # A client must never touch a local path; point it somewhere that would
    # show up if it did.
    client = Settings(
        kuzu_path=tmp_path / "client-must-not-exist",
        kuzu_role="client",
        graph_rpc_url="http://owner",
        internal_graph_token="s3cret",
    )
    owner.internal_graph_token = "s3cret"
    monkeypatch.setattr(graph, "get_settings", lambda: _role.get(owner))
    monkeypatch.setattr("archivum.api.internal_graph.get_settings", lambda: owner)
    return owner, client


@pytest.fixture
async def owner_client(roles, monkeypatch):
    owner, _ = roles
    monkeypatch.setattr(graph, "_db", None)
    await graph.init_graph(owner)

    app = FastAPI()
    app.include_router(internal_graph_router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://owner"
    ) as client:
        monkeypatch.setattr(graph, "_rpc_client_override", client)
        yield client
    if graph._db is not None:
        graph._db.close()


@pytest.fixture
def no_new_databases(monkeypatch):
    """Fail loudly if anything opens another kuzu.Database after the owner's."""
    opened: list[str] = []
    real = kuzu.Database

    def spy(*args, **kwargs):
        opened.append(str(args[0]) if args else "?")
        return real(*args, **kwargs)

    monkeypatch.setattr(kuzu, "Database", spy)
    return opened


def _as(settings: Settings, coro_fn, *args, **kwargs) -> asyncio.Task:
    ctx = contextvars.copy_context()
    ctx.run(_role.set, settings)
    return asyncio.create_task(coro_fn(*args, **kwargs), context=ctx)


async def test_client_role_reads_and_writes_through_owner_under_concurrent_writes(
    roles, owner_client, no_new_databases
):
    owner, client = roles
    owner_db = graph._db
    assert owner_db is not None

    await graph._local_upsert_page("target", "Target", "default")
    duration = 2.0
    deadline = time.monotonic() + duration

    async def owner_writer() -> int:
        n = 0
        while time.monotonic() < deadline:
            await graph.upsert_page(f"owner-{n % 40}", f"Owner {n}", "default")
            await graph.add_reference(f"owner-{n % 40}", "target", "default")
            n += 1
        return n

    async def client_worker(i: int) -> int:
        calls = 0
        while time.monotonic() < deadline:
            await graph.upsert_page(f"client-{i}", f"Client {i}", "default")
            await graph.add_reference(f"client-{i}", "target", "default")
            backlinks = await graph.get_backlinks("target", "default")
            assert isinstance(backlinks, list)
            calls += 3
            # The owner process stays the only one with a handle, throughout.
            assert graph._db is owner_db
        return calls

    writer = _as(owner, owner_writer)
    workers = [_as(client, client_worker, i) for i in range(24)]
    results = await asyncio.gather(writer, *workers, return_exceptions=True)

    failures = [r for r in results if isinstance(r, BaseException)]
    assert not failures, failures
    owner_writes, *client_calls = results
    assert owner_writes > 0
    assert all(c > 0 for c in client_calls), client_calls

    # The client calls did real work on the owner's database, not a silent
    # no-op: every client page is linked to the target, as are the owner's.
    final = await _as(client, graph.get_backlinks, "target", "default")
    slugs = {b["slug"] for b in final}
    assert {f"client-{i}" for i in range(24)} <= slugs
    assert any(s.startswith("owner-") for s in slugs)

    assert no_new_databases == []
    assert graph._db is owner_db
    assert not client.kuzu_path.exists()


async def test_client_role_init_graph_opens_nothing(roles, monkeypatch, no_new_databases):
    _, client = roles
    monkeypatch.setattr(graph, "_db", None)

    await graph.init_graph(client)

    assert graph._db is None
    assert no_new_databases == []
    assert not client.kuzu_path.exists()


async def test_unreachable_owner_is_graph_unavailable_not_an_httpx_error(roles, monkeypatch):
    _, client = roles
    client.graph_rpc_url = "http://127.0.0.1:9"  # discard port: nothing listens
    monkeypatch.setattr(graph, "_rpc_client_override", None)

    with pytest.raises(graph.GraphUnavailableError, match="get_backlinks"):
        await _as(client, graph.get_backlinks, "target", "default")


async def test_internal_endpoint_rejects_unknown_ops_and_bad_tokens(roles, owner_client):
    unknown = await owner_client.post(
        "/internal/graph/_get_conn", json={}, headers={"X-Internal-Token": "s3cret"}
    )
    assert unknown.status_code == 404

    wrong = await owner_client.post(
        "/internal/graph/get_backlinks",
        json={"slug": "x"},
        headers={"X-Internal-Token": "nope"},
    )
    assert wrong.status_code == 403

    ok = await owner_client.post(
        "/internal/graph/get_backlinks",
        json={"slug": "x"},
        headers={"X-Internal-Token": "s3cret"},
    )
    assert ok.status_code == 200
    assert ok.json() == {"result": []}


async def test_owner_side_failure_reaches_client_as_graph_unavailable(roles, owner_client, monkeypatch):
    _, client = roles

    async def boom(**_kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(graph, "_local_get_backlinks", boom)

    with pytest.raises(graph.GraphUnavailableError, match="disk on fire"):
        await _as(client, graph.get_backlinks, "target", "default")


def test_lock_contention_is_retried_then_normalized(monkeypatch):
    monkeypatch.setattr(graph.time, "sleep", lambda _s: None)

    class FlakyConn:
        calls = 0

        def execute(self, query, params=None):
            FlakyConn.calls += 1
            if FlakyConn.calls < 3:
                raise RuntimeError("IO exception: Could not set lock on file")
            return "ok"

    assert graph._execute_with_retry(FlakyConn(), "RETURN 1") == "ok"
    assert FlakyConn.calls == 3

    class LockedConn:
        def execute(self, query, params=None):
            raise RuntimeError("Could not set lock on file")

    with pytest.raises(graph.GraphUnavailableError):
        graph._execute_with_retry(LockedConn(), "RETURN 1")

    class BrokenConn:
        calls = 0

        def execute(self, query, params=None):
            BrokenConn.calls += 1
            raise RuntimeError("Binder exception: table Nope does not exist")

    # Anything that is not lock contention is not retried and keeps its type,
    # so the existing per-function handling of it is unchanged.
    with pytest.raises(RuntimeError, match="Binder"):
        graph._execute_with_retry(BrokenConn(), "RETURN 1")
    assert BrokenConn.calls == 1


def test_every_allowed_op_has_a_dispatcher_with_its_local_twins_signature():
    import inspect

    from archivum.api.internal_graph import _ALLOWED_OPS

    public = {
        name
        for name, fn in vars(graph).items()
        if inspect.iscoroutinefunction(fn)
        and not name.startswith("_")
        and name != "init_graph"
    }
    assert public == set(_ALLOWED_OPS)
    for op in _ALLOWED_OPS:
        # The client sends its arguments by name and the owner splats them
        # into `_local_<op>`, so the names have to match exactly.
        assert inspect.signature(getattr(graph, op)) == inspect.signature(
            getattr(graph, f"_local_{op}")
        ), op
