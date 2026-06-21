from __future__ import annotations

from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.asyncio
async def test_stdio_server_lists_expected_tools():
    backend_dir = Path(__file__).resolve().parents[2] / "apps" / "backend"
    server = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "archivum.mcp.server", "--stdio"],
        cwd=backend_dir,
    )

    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            response = await session.list_tools()

    tool_names = {tool.name for tool in response.tools}
    assert {
        "ingest_source",
        "search_wiki",
        "list_pages",
        "get_page",
        "write_page",
        "query",
        "graph_neighbors",
        "lint_wiki",
        "export_graph_demo",
        "dispatch_command",
    }.issubset(tool_names)
