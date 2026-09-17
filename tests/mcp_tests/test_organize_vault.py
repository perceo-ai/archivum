"""Agents keeping the vault tidy while they work.

Agents could already create and rewrite pages. They could not move one, retire
one, or make a folder to put things in — every organising verb existed in REST
and none of it was reachable over MCP, so a vault an agent filled was a vault
only a human could tidy.

Deliberately no delete. Retiring a page archives it, so nothing an agent does
to this vault is unrecoverable.
"""

from __future__ import annotations

import pytest

from archivum.config import Settings
from archivum.db import sqlite
from archivum.mcp import server


@pytest.fixture(autouse=True)
def _direct_tool_calls_bypass_transport_auth():
    server.set_transport("stdio")
    try:
        yield
    finally:
        server.set_transport("http")


@pytest.fixture
def temp_settings(tmp_path):
    return Settings(
        db_path=tmp_path / "archivum.db",
        wiki_dir=tmp_path / "wiki",
        raw_dir=tmp_path / "raw",
        kuzu_path=tmp_path / "kuzu",
    )


@pytest.fixture
async def vault(temp_settings, monkeypatch):
    """A real vault on disk, with the two network services stubbed.

    Qdrant is a running server this test does not need: what is under test is
    where a page ends up and which links point at it, all of which live in
    SQLite, the markdown file, and Kuzu. Leaving the real client in place makes
    every write block on a connection instead of failing.
    """
    from archivum.db import graph
    from archivum.db import qdrant_client as qdrant

    async def _noop(*args, **kwargs):
        return None

    for name in ("upsert_page", "delete_page", "init_collection"):
        if hasattr(qdrant, name):
            monkeypatch.setattr(qdrant, name, _noop)

    # Kuzu caches its connection in a module global, built from get_settings()
    # on first use. Left alone it opens /data/kuzu, which is the container's
    # path and read-only here — and a move that cannot rename a graph node
    # fails outright rather than degrading.
    monkeypatch.setattr(graph, "_conn", None, raising=False)
    monkeypatch.setattr(graph, "_db", None, raising=False)
    await graph.init_graph(temp_settings)

    monkeypatch.setattr(server, "settings", temp_settings)
    monkeypatch.setattr("archivum.api.pages.get_settings", lambda: temp_settings)
    monkeypatch.setattr("archivum.indexing.get_settings", lambda: temp_settings, raising=False)
    temp_settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    await sqlite.init_db(temp_settings)
    return temp_settings


def _why(result):
    """Failures should say which operation failed and what it said.

    Asserting on a count alone produces `assert 0 == 1`, which sends you back
    to the code to find out what broke.
    """
    return "; ".join(
        f"[{r['op']}] {'ok' if r['ok'] else r['detail']}" for r in result["results"]
    ) or "no operations"


async def _page(settings, title, slug, content="Body.\n"):
    """Write a page the way the worker does, without needing the worker.

    `write_page` enqueues a job and waits for the background writer, which no
    test runs. Calling what that writer calls gives a real page — file on
    disk, row in SQLite, links projected — with no queue in the way.
    """
    from archivum.page_write_queue import apply_page_write

    return await apply_page_write(
        title=title,
        content=content,
        slug=slug,
        tags=[],
        authored_by="agent",
        wiki_id="default",
        settings=settings,
    )


@pytest.mark.asyncio
async def test_a_page_can_be_refiled(vault):
    await _page(vault, "Kigali notes", "inbox/kigali-notes")

    result = await server.organize_vault(
        [{"op": "move", "slug": "inbox/kigali-notes", "to": "projects/kigali/notes"}]
    )

    assert result["applied"] == 1, _why(result)
    assert (await server.get_page("projects/kigali/notes"))["slug"] == "projects/kigali/notes"
    assert (await server.get_page("inbox/kigali-notes")).get("error") == "page_not_found"


@pytest.mark.asyncio
async def test_moving_a_page_rewrites_links_that_pointed_at_it(vault):
    """The reason this reuses the browser's mover rather than renaming a file.

    A move that leaves [[old-slug]] behind quietly breaks the graph, and the
    breakage only shows up later as a page with no backlinks.
    """
    await _page(vault, "Target", "inbox/target")
    await _page(vault, "Pointer", "notes/pointer", content="See [[inbox/target]] for detail.\n")

    await server.organize_vault(
        [{"op": "move", "slug": "inbox/target", "to": "projects/target"}]
    )

    pointer = await server.get_page("notes/pointer")
    assert "[[projects/target]]" in pointer["content"]
    assert "[[inbox/target]]" not in pointer["content"]


@pytest.mark.asyncio
async def test_archiving_retires_a_page_without_destroying_it(vault):
    """There is no delete op, on purpose: page deletion is an unlink with no
    trash and no history, so an agent cannot be given it."""
    await _page(vault, "Stale", "notes/stale")

    result = await server.organize_vault([{"op": "archive", "slug": "notes/stale"}])

    assert result["applied"] == 1, _why(result)
    archived = await server.get_page("archive/notes/stale")
    assert archived.get("error") != "page_not_found"
    assert (await server.get_page("notes/stale")).get("error") == "page_not_found"


@pytest.mark.asyncio
async def test_there_is_no_delete_operation(vault):
    await _page(vault, "Keep", "notes/keep")

    result = await server.organize_vault([{"op": "delete", "slug": "notes/keep"}])

    assert result["failed"] == 1, _why(result)
    assert (await server.get_page("notes/keep")).get("error") != "page_not_found"
    # The refusal has to name the alternative, or an agent just tries again.
    assert "archive" in result["results"][0]["detail"].lower()


@pytest.mark.asyncio
async def test_folders_can_be_created_to_put_things_in(vault):
    result = await server.organize_vault([{"op": "create_folder", "path": "projects/kigali"}])

    assert result["applied"] == 1, _why(result)
    folders = [f["path"] for f in await sqlite.list_folders("default")]
    assert "projects/kigali" in folders


@pytest.mark.asyncio
async def test_a_folder_can_be_renamed_with_its_pages(vault):
    await _page(vault, "One", "notes/one")

    result = await server.organize_vault(
        [{"op": "rename_folder", "path": "notes", "to": "reference"}]
    )

    assert result["applied"] == 1, _why(result)
    assert (await server.get_page("reference/one")).get("error") != "page_not_found"


@pytest.mark.asyncio
async def test_operations_apply_in_order_so_a_reorg_reads_as_a_plan(vault):
    """The whole point of a batch: make the folder, then file into it."""
    await _page(vault, "Notes", "inbox/notes")

    result = await server.organize_vault(
        [
            {"op": "create_folder", "path": "projects/kigali"},
            {"op": "move", "slug": "inbox/notes", "to": "projects/kigali/notes"},
        ]
    )

    assert result["applied"] == 2, _why(result)
    assert (await server.get_page("projects/kigali/notes")).get("error") != "page_not_found"


@pytest.mark.asyncio
async def test_one_bad_operation_does_not_abandon_the_rest(vault):
    """A ten-step reorganisation must not die on step three and leave the vault
    half-moved with no report of where it stopped."""
    await _page(vault, "Good", "inbox/good")

    result = await server.organize_vault(
        [
            {"op": "move", "slug": "inbox/missing", "to": "projects/missing"},
            {"op": "move", "slug": "inbox/good", "to": "projects/good"},
        ]
    )

    assert result["applied"] == 1, _why(result)
    assert result["failed"] == 1, _why(result)
    assert (await server.get_page("projects/good")).get("error") != "page_not_found"


@pytest.mark.asyncio
async def test_every_operation_reports_its_own_outcome(vault):
    await _page(vault, "Good", "inbox/good")

    result = await server.organize_vault(
        [
            {"op": "move", "slug": "inbox/good", "to": "projects/good"},
            {"op": "move", "slug": "inbox/missing", "to": "projects/missing"},
        ]
    )

    assert [r["ok"] for r in result["results"]] == [True, False]
    assert result["results"][1]["detail"]


@pytest.mark.asyncio
async def test_an_unknown_operation_is_refused_by_name(vault):
    result = await server.organize_vault([{"op": "reticulate", "slug": "x"}])

    assert result["failed"] == 1, _why(result)
    assert "reticulate" in result["results"][0]["detail"]


@pytest.mark.asyncio
async def test_a_move_that_would_overwrite_is_refused(vault):
    """Two pages merged by accident is exactly the unrecoverable outcome the
    absence of a delete op is meant to avoid."""
    await _page(vault, "First", "notes/first")
    await _page(vault, "Second", "notes/second")

    result = await server.organize_vault(
        [{"op": "move", "slug": "notes/first", "to": "notes/second"}]
    )

    assert result["failed"] == 1, _why(result)
    assert (await server.get_page("notes/first")).get("error") != "page_not_found"


@pytest.mark.asyncio
async def test_an_empty_plan_is_not_an_error(vault):
    result = await server.organize_vault([])

    assert result["applied"] == 0, _why(result)
    assert result["failed"] == 0, _why(result)


@pytest.mark.asyncio
async def test_get_page_can_report_what_links_here(vault):
    """An agent deciding whether to refile a page needs to know what points at
    it, and a separate tool for that is a tool nobody remembers to call."""
    await _page(vault, "Target", "notes/target")
    await _page(vault, "Pointer", "notes/pointer", content="See [[notes/target]].\n")

    page = await server.get_page("notes/target", include_backlinks=True)

    assert "backlinks" in page


@pytest.mark.asyncio
async def test_get_page_stays_lean_by_default(vault):
    """Backlinks cost a graph query, so they are opt-in rather than always on."""
    await _page(vault, "Target", "notes/target")

    assert "backlinks" not in await server.get_page("notes/target")


@pytest.mark.asyncio
async def test_writing_a_nested_page_registers_its_folders(vault):
    """A folder is a row, not just a path segment.

    `move` and `duplicate` both create parent folder rows; the queue writer —
    the path MCP `write_page` takes — did not. An agent writing `notes/one`
    therefore produced a page inside a folder the file tree could not show and
    `rename_folder` reported as missing.
    """
    await _page(vault, "One", "projects/kigali/one")

    folders = {f["path"] for f in await sqlite.list_folders("default")}

    assert "projects" in folders
    assert "projects/kigali" in folders
