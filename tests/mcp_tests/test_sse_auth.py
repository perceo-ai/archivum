from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.sse import sse_client
from starlette.testclient import TestClient

from archivum.config import Settings
from archivum.mcp import server


@asynccontextmanager
async def _serve_app(app):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error", lifespan="off")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.01)
        assert server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, timeout=5)


def test_sse_transport_rejects_missing_bearer_token():
    app = server.create_mcp(Settings(mcp_api_key="valid-token")).sse_app(mount_path="/")

    response = TestClient(app).get("/sse")

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"


def test_sse_message_post_rejects_missing_bearer_token():
    app = server.create_mcp(Settings(mcp_api_key="valid-token")).sse_app(mount_path="/")

    response = TestClient(app).post("/messages/", json={})

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_token"


@pytest.mark.asyncio
async def test_sse_transport_allows_valid_configured_bearer_token_to_list_tools():
    app = server.create_mcp(Settings(mcp_api_key="valid-token")).sse_app(mount_path="/")

    async with _serve_app(app) as base_url:
        async with sse_client(
            f"{base_url}/sse",
            headers={"Authorization": "Bearer valid-token"},
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()
                tool_response = await session.call_tool("dispatch_command", {"command": "help"})

    assert "list_pages" in {tool.name for tool in response.tools}
    assert not tool_response.isError
