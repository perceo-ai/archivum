"""The MCP `get_page` tool in client role, against a real owner process.

This is the production topology, not a simulation of it: the owner is a
separate OS process (uvicorn serving the internal graph router) that holds
the Kuzu file and writes to it continuously. This test process plays `mcp`
with `kuzu_role="client"`. If anything here opened the file locally, Kuzu
would refuse it with the very "Could not set lock on file" this fixes.

Call surface: `server.mcp._tool_manager.call_tool("get_page", ...)`. That is
the registered FastMCP `Tool`, so arguments go through the same pydantic
validation a transport request does. (`@mcp.tool()` returns the undecorated
function, so `server.get_page` would also work, but would skip that.) Bearer
auth is a transport concern; as in test_server.py, run as stdio to skip it.

The owner's write loop is graph writes (`upsert_page`/`add_reference`), not
the LLM ingest pipeline, which would need a model to run.
"""

from __future__ import annotations

import asyncio
import os
import socket
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx
import pytest

import archivum.db.graph as graph
from archivum.config import Settings
from archivum.db import sqlite
from archivum.mcp import server

_TOKEN = "test-internal-token"

_OWNER = textwrap.dedent(
    """
    import asyncio
    import sys
    from contextlib import asynccontextmanager

    import uvicorn
    from fastapi import FastAPI

    from archivum.api.internal_graph import router
    from archivum.db import graph

    writes = 0

    @asynccontextmanager
    async def lifespan(app):
        await graph.init_graph()
        await graph.upsert_page("target", "Target", "default")

        async def write_loop():
            global writes
            while True:
                slug = f"owner-{writes % 40}"
                await graph.upsert_page(slug, f"Owner {writes}", "default")
                await graph.add_reference(slug, "target", "default")
                writes += 1
                await asyncio.sleep(0)

        task = asyncio.create_task(write_loop())
        yield
        task.cancel()

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)

    @app.get("/writes")
    async def count():
        return {"writes": writes}

    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")
    """
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def owner_process(tmp_path):
    port = _free_port()
    backend = Path(__file__).resolve().parents[2] / "apps" / "backend"
    env = {
        **os.environ,
        "PYTHONPATH": str(backend),
        "KUZU_PATH": str(tmp_path / "owner-kuzu"),
        "KUZU_ROLE": "owner",
        "INTERNAL_GRAPH_TOKEN": _TOKEN,
    }
    proc = subprocess.Popen(
        [sys.executable, "-c", _OWNER, str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 60
    try:
        while True:
            if proc.poll() is not None:
                pytest.fail(f"owner exited early:\n{proc.stdout.read()}")
            try:
                if httpx.get(f"{url}/writes", timeout=1).json()["writes"] > 0:
                    break
            except (httpx.HTTPError, ValueError, KeyError):
                pass
            if time.monotonic() > deadline:
                pytest.fail("owner did not start writing in time")
            time.sleep(0.1)
        yield url, tmp_path / "owner-kuzu"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
async def client_role(tmp_path, owner_process, monkeypatch):
    url, owner_kuzu = owner_process
    client = Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        # The owner's own path: opening it here would fail on the lock.
        kuzu_path=owner_kuzu,
        kuzu_role="client",
        graph_rpc_url=url,
        internal_graph_token=_TOKEN,
    )
    monkeypatch.setattr(graph, "get_settings", lambda: client)
    monkeypatch.setattr(graph, "_db", None)
    monkeypatch.setattr(graph, "_rpc_client_override", None)
    monkeypatch.setattr(server, "settings", client)
    monkeypatch.setattr(sqlite, "_db_path", None)
    server.set_transport("stdio")

    await sqlite.init_db(client)
    await sqlite.upsert_page("target", "Target", "# Target", [], wiki_id="default")
    await graph.init_graph(client)
    try:
        yield url
    finally:
        server.set_transport("http")


async def test_get_page_with_backlinks_in_client_role_never_fails(client_role):
    url = client_role
    async with httpx.AsyncClient() as http:
        writes_before = (await http.get(f"{url}/writes")).json()["writes"]

    gate = asyncio.Semaphore(10)

    async def one_call(i: int):
        async with gate:
            # Client-side writes too, as the MCP server's own ingest makes.
            await graph.upsert_page(f"mcp-{i}", f"MCP {i}", "default")
            await graph.add_reference(f"mcp-{i}", "target", "default")
            return await server.mcp._tool_manager.call_tool(
                "get_page",
                {"slug": "target", "wiki_id": "default", "include_backlinks": True},
            )

    results = await asyncio.gather(*(one_call(i) for i in range(50)), return_exceptions=True)

    failures = [r for r in results if isinstance(r, BaseException)]
    assert not failures, failures
    for page in results:
        assert page["slug"] == "target"
        assert isinstance(page["backlinks"], list)

    async with httpx.AsyncClient() as http:
        writes_after = (await http.get(f"{url}/writes")).json()["writes"]
    # The owner kept writing the whole time the client was reading.
    assert writes_after > writes_before

    final = results[-1]["backlinks"] + (await graph.get_backlinks("target", "default"))
    slugs = {b["slug"] for b in final}
    assert any(s.startswith("owner-") for s in slugs)
    assert {f"mcp-{i}" for i in range(50)} <= slugs

    # This process never held a Kuzu handle.
    assert graph._db is None
