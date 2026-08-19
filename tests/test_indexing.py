"""The vault is editable by hand, so the indexes have to be able to catch up."""

import pytest

from archivum.config import Settings
from archivum.db import sqlite as sqlite_mod
from archivum.indexing import (
    ReindexResult,
    reconcile_vault,
    reindex_page,
    slug_for_path,
)


@pytest.fixture
async def env(tmp_path):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
    )
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    await sqlite_mod.init_db(settings)
    return settings


def write(settings: Settings, slug: str, text: str) -> None:
    path = settings.wiki_dir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def test_a_file_written_by_hand_becomes_a_page(env):
    write(env, "topics/retrieval", "# Retrieval design\n\nTwo passes.\n")

    result = await reindex_page("topics/retrieval", wiki_id="default", settings=env)

    assert result.action == "indexed"
    row = await sqlite_mod.get_page("topics/retrieval", "default")
    assert row is not None
    assert row["title"] == "Retrieval design"
    assert "Two passes." in row["content"]


async def test_frontmatter_supplies_title_and_tags(env):
    write(
        env,
        "notes/a",
        '---\ntitle: A better title\ntags: [retrieval, "sleep"]\n---\n\n# Ignored heading\n',
    )

    await reindex_page("notes/a", wiki_id="default", settings=env)

    row = await sqlite_mod.get_page("notes/a", "default")
    assert row["title"] == "A better title"
    assert "retrieval" in row["tags"] and "sleep" in row["tags"]


async def test_reindexing_an_unchanged_page_is_a_no_op(env):
    write(env, "notes/a", "# A\n")
    assert (await reindex_page("notes/a", wiki_id="default", settings=env)).action == "indexed"

    # Watchers are noisy and reconcile is wholesale, so repeats must be cheap.
    again = await reindex_page("notes/a", wiki_id="default", settings=env)
    assert again.action == "unchanged"

    forced = await reindex_page("notes/a", wiki_id="default", settings=env, force=True)
    assert forced.action == "indexed"


async def test_editing_the_file_outside_the_app_is_picked_up(env):
    write(env, "notes/a", "# A\n\nfirst\n")
    await reindex_page("notes/a", wiki_id="default", settings=env)

    write(env, "notes/a", "# A\n\nsecond\n")
    result = await reindex_page("notes/a", wiki_id="default", settings=env)

    assert result.action == "indexed"
    row = await sqlite_mod.get_page("notes/a", "default")
    assert "second" in row["content"]


async def test_deleting_the_file_removes_the_page(env):
    write(env, "notes/a", "# A\n")
    await reindex_page("notes/a", wiki_id="default", settings=env)

    (env.wiki_dir / "notes/a.md").unlink()
    result = await reindex_page("notes/a", wiki_id="default", settings=env)

    assert result.action == "removed"
    assert await sqlite_mod.get_page("notes/a", "default") is None


async def test_reconcile_catches_up_in_both_directions(env):
    # A page the app knows about, whose file someone deleted.
    write(env, "notes/gone", "# Gone\n")
    await reindex_page("notes/gone", wiki_id="default", settings=env)
    (env.wiki_dir / "notes/gone.md").unlink()

    # A file the app has never seen.
    write(env, "notes/new", "# New\n")

    results = await reconcile_vault(wiki_id="default", settings=env)
    by_slug = {r.slug: r.action for r in results}

    assert by_slug["notes/new"] == "indexed"
    assert by_slug["notes/gone"] == "removed"
    assert await sqlite_mod.get_page("notes/new", "default") is not None
    assert await sqlite_mod.get_page("notes/gone", "default") is None


async def test_projection_failures_degrade_rather_than_raise(env, monkeypatch):
    """Losing the embedding store must not lose the page."""
    from archivum.db import qdrant_client as qdrant

    async def boom(*args, **kwargs):
        raise RuntimeError("qdrant unreachable")

    monkeypatch.setattr(qdrant, "upsert_page", boom)
    write(env, "notes/a", "# A\n")

    result = await reindex_page("notes/a", wiki_id="default", settings=env)

    assert result.action == "indexed"
    assert "search" in result.degraded
    assert result.ok is False
    # The canonical row still landed.
    assert await sqlite_mod.get_page("notes/a", "default") is not None


def test_slug_for_path_ignores_anything_outside_the_vault(env):
    assert slug_for_path(env, env.wiki_dir / "a/b.md") == "a/b"
    assert slug_for_path(env, env.wiki_dir / "a/b.txt") is None
    assert slug_for_path(env, env.wiki_dir.parent / "elsewhere.md") is None


def test_result_reports_health():
    assert ReindexResult(slug="a").ok is True
    assert ReindexResult(slug="a", degraded=["search"]).ok is False


async def test_reindex_projects_into_the_graph_without_a_rebuild(env, tmp_path):
    """The graph used to converge only on a manual rebuild, which is why the
    node list and the community view disagreed."""
    from archivum.db import graph as graph_mod

    settings = env
    settings.kuzu_path = tmp_path / "kuzu"
    settings.kuzu_path.mkdir(parents=True, exist_ok=True)
    await graph_mod.init_graph(settings)

    write(settings, "topics/a", "# A\n\nlinks to [[topics/b]]\n")
    write(settings, "topics/b", "# B\n")
    await reindex_page("topics/b", wiki_id="default", settings=settings)
    result = await reindex_page("topics/a", wiki_id="default", settings=settings)

    assert result.action == "indexed"
    # Qdrant is not running in tests, so "search" is expected; the graph is not.
    assert [d for d in result.degraded if d.startswith("graph")] == []

    data = await graph_mod.get_all_nodes_edges("default")
    node_ids = {node["id"] for node in data["nodes"]}
    assert "topics/a" in node_ids and "topics/b" in node_ids

    edges = {(edge["from"], edge["to"]) for edge in data["edges"]}
    assert ("topics/a", "topics/b") in edges


async def test_removing_a_page_clears_it_from_the_graph(env, tmp_path):
    from archivum.db import graph as graph_mod

    settings = env
    settings.kuzu_path = tmp_path / "kuzu2"
    settings.kuzu_path.mkdir(parents=True, exist_ok=True)
    await graph_mod.init_graph(settings)

    write(settings, "topics/a", "# A\n")
    await reindex_page("topics/a", wiki_id="default", settings=settings)
    (settings.wiki_dir / "topics/a.md").unlink()
    await reindex_page("topics/a", wiki_id="default", settings=settings)

    data = await graph_mod.get_all_nodes_edges("default")
    assert "topics/a" not in {node["id"] for node in data["nodes"]}
