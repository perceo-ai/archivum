from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager

import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client
from starlette.testclient import TestClient

from archivum.config import Settings
from archivum.mcp import server


@asynccontextmanager
async def _serve_app(app):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    uvicorn_server = uvicorn.Server(config)
    task = asyncio.create_task(uvicorn_server.serve())
    try:
        for _ in range(200):
            if uvicorn_server.started:
                break
            await asyncio.sleep(0.01)
        assert uvicorn_server.started
        yield f"http://127.0.0.1:{port}"
    finally:
        uvicorn_server.should_exit = True
        await asyncio.wait_for(task, timeout=5)


def _app():
    return server.build_http_app(server.create_mcp(Settings(mcp_api_key="valid-token")))


def test_streamable_http_endpoint_rejects_missing_bearer_token():
    response = TestClient(_app()).post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        headers={"Accept": "application/json, text/event-stream"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_streamable_http_serves_tools_at_mcp():
    """Codex and other rmcp clients POST initialize straight at the configured
    URL. Serving only /sse answered that POST with 405 Method Not Allowed."""
    async with _serve_app(_app()) as base_url:
        async with streamablehttp_client(
            f"{base_url}/mcp",
            headers={"Authorization": "Bearer valid-token"},
        ) as (read, write, _get_session_id):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()

    assert "list_pages" in {tool.name for tool in response.tools}


@pytest.mark.asyncio
async def test_sse_still_works_on_the_combined_app():
    async with _serve_app(_app()) as base_url:
        async with sse_client(
            f"{base_url}/sse",
            headers={"Authorization": "Bearer valid-token"},
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                response = await session.list_tools()

    assert "list_pages" in {tool.name for tool in response.tools}
