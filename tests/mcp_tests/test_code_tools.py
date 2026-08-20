"""Agents should be able to reach code memory, not just prose memory.

Archivum's whole point for a developer is that an agent can ask what the code
is and why it is that way. Every other kind of memory had an MCP tool; code had
none, so the repository graph was invisible to the agents it was built for.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings

GEO = (
    "def haversine(lat, lon):\n"
    "    return normalise(lat) + normalise(lon)\n"
    "\n\n"
    "def normalise(value):\n"
    "    return value % 360\n"
)


@pytest.fixture(autouse=True)
def _needs_git():
    if shutil.which("git") is None:
        pytest.skip("git not available")


@pytest.fixture
def vault(tmp_path, monkeypatch):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
        code_cache_dir=tmp_path / "code-cache",
        mcp_api_key="",
    )
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("archivum.mcp.server.settings", settings, raising=False)
    return settings


def make_repo(root: Path) -> Path:
    repo = root / "atlas"
    repo.mkdir()
    (repo / "geo.py").write_text(GEO, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@e.com", "-c", "user.name=T",
         "commit", "-q", "-m", "x"],
        check=True,
    )
    return repo


async def test_an_agent_can_index_a_repository(vault, tmp_path, mock_kuzu_conn):
    from archivum.mcp.server import index_repository

    await sqlite_mod.init_db(vault)
    repo = make_repo(tmp_path)

    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
    ):
        result = await index_repository(str(repo))

    assert result["scope"] == "repo:default:atlas"
    assert result["status"] == "ready"
    assert result["nodes"] > 0
    assert result["pages"] > 0, "indexing should leave readable pages behind"


async def test_an_agent_can_list_what_repositories_are_known(vault, tmp_path, mock_kuzu_conn):
    from archivum.mcp.server import index_repository, list_repositories

    await sqlite_mod.init_db(vault)
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
    ):
        await index_repository(str(make_repo(tmp_path)))

    listed = await list_repositories()
    assert [entry["name"] for entry in listed] == ["atlas"]


async def test_an_agent_asking_about_code_gets_cited_records(vault, tmp_path, mock_kuzu_conn):
    from archivum.mcp.server import index_repository, retrieve_code_context

    await sqlite_mod.init_db(vault)
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
    ):
        await index_repository(str(make_repo(tmp_path)))

    package = await retrieve_code_context("haversine", repo="atlas")
    labels = {node["label"] for node in package["nodes"]}
    assert "haversine" in labels
    assert package["citations"], "code context must carry citations into files"
