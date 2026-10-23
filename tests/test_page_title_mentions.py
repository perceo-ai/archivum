"""Pages reference the other pages they name, even without brackets.

Hand-written pages talk about each other in prose — "the Archductor Requirements
cover this" — not in `[[wikilink]]` syntax, so a vault of them came back as all
islands even though their text says how they relate. The title is read off the
page on every index, the same way entity mentions are, and recorded as an
inferred reference. The page's file is never touched.
"""

import aiosqlite
import pytest

from archivum.config import Settings
from archivum.db import sqlite as sqlite_mod
from archivum.indexing import reconcile_vault, reindex_page
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.pages_to_knowledge import sync_page_to_knowledge


@pytest.fixture
async def repo():
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await init_knowledge_schema(conn)
        yield KnowledgeRepository(conn)


async def _page(repo, slug: str, title: str, markdown: str = "") -> None:
    await sync_page_to_knowledge(
        repo, slug=slug, title=title, markdown=markdown or f"# {title}\n", wiki_id="default"
    )


async def _references(repo, slug: str = "notes") -> dict[str, str]:
    """Referenced page id -> how the reference was made."""
    return {
        rel.dst_id: rel.extraction_method
        for rel in await repo.list_relationships(scope="wiki:default")
        if rel.rel_type == "references" and rel.src_id == f"page:default:{slug}"
    }


async def test_a_page_references_the_pages_it_names(repo):
    await _page(repo, "projects/archductor", "Archductor")
    await _page(repo, "projects/archductor-requirements", "Archductor Requirements")

    await _page(
        repo, "notes", "Notes",
        "Archductor runs the agents; the Archductor Requirements list what it needs.",
    )

    assert await _references(repo) == {
        "page:default:projects/archductor": "INFERRED",
        "page:default:projects/archductor-requirements": "INFERRED",
    }


async def test_a_title_inside_a_longer_title_is_not_a_second_reference(repo):
    """"the Ledger Design" names the design page, not the page titled "Ledger"."""
    await _page(repo, "code/ledger/index", "Ledger")
    await _page(repo, "projects/ledger-design", "Ledger Design")

    await _page(repo, "notes", "Notes", "We sketched the Ledger Design first.")

    assert await _references(repo) == {"page:default:projects/ledger-design": "INFERRED"}


async def test_a_title_inside_a_longer_word_is_not_a_reference(repo):
    await _page(repo, "projects/loop", "Loop")

    await _page(repo, "notes", "Notes", "Loopback interfaces are fine.")

    assert await _references(repo) == {}


async def test_a_title_has_to_be_written_the_way_it_is_titled(repo):
    """"Timeline" the page is not a timeline in a sentence."""
    await _page(repo, "projects/timeline", "Timeline")

    await _page(repo, "notes", "Notes", "the timeline slipped again")

    assert await _references(repo) == {}


async def test_a_bare_lowercase_title_is_never_matched(repo):
    """Generated code pages are titled "client", "update", "layout"."""
    await _page(repo, "code/app/client", "client")

    await _page(repo, "notes", "Notes", "Restart the client after the update.")

    assert await _references(repo) == {}


async def test_very_short_titles_are_not_matched(repo):
    await _page(repo, "projects/go", "Go")

    await _page(repo, "notes", "Notes", "Go and see. Go now.")

    assert await _references(repo) == {}


async def test_an_acronym_title_is_matched_when_written_as_one(repo):
    await _page(repo, "topics/jwt", "JWT")

    await _page(repo, "notes", "Notes", "Auth uses a JWT cookie, not a jwt-ish token.")

    assert await _references(repo) == {"page:default:topics/jwt": "INFERRED"}


async def test_a_page_does_not_reference_itself_or_its_namesake(repo):
    """Two pages can share a title; writing your own title names neither."""
    await _page(repo, "old/archivum", "Archivum")

    await _page(repo, "notes", "Archivum", "# Archivum\n\nArchivum remembers things.")

    assert await _references(repo) == {}


async def test_a_wikilink_keeps_its_explicit_edge(repo):
    """An inferred edge must not overwrite the one the author actually wrote."""
    await _page(repo, "projects/archfleet", "Archfleet")

    await _page(repo, "notes", "Notes", "Archfleet is next. See [[projects/archfleet]].")

    assert await _references(repo) == {"page:default:projects/archfleet": "USER_AUTHORED"}


async def test_editing_a_page_drops_references_it_no_longer_makes(repo):
    await _page(repo, "projects/archivum", "Archivum")
    await _page(repo, "notes", "Notes", "About Archivum.")
    assert await _references(repo)

    await _page(repo, "notes", "Notes", "About nothing now.")

    assert await _references(repo) == {}, "a stale edge is a claim the page no longer makes"


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


async def test_a_forced_reconcile_backfills_pages_indexed_before_this_existed(env, mock_kuzu_conn):
    """No separate backfill: rebuilding the vault re-reads every page."""
    pages = {
        "projects/archductor": "# Archductor\n\nRuns agents. Archivum stores what they learn.\n",
        "projects/archivum": "# Archivum\n\nThe memory Archductor agents share.\n",
    }
    for slug, text in pages.items():
        path = env.wiki_dir / f"{slug}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    await reconcile_vault(wiki_id="default", settings=env)

    # The state a vault indexed before this change is in: pages, no references.
    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        for slug in pages:
            await repo.delete_relationships(
                src_id=f"page:default:{slug}", rel_types={"references"}
            )
        assert await _references(repo, "projects/archductor") == {}

    await reconcile_vault(wiki_id="default", settings=env, force=True)

    async with sqlite_mod.get_db() as conn:
        repo = KnowledgeRepository(conn)
        assert await _references(repo, "projects/archductor") == {
            "page:default:projects/archivum": "INFERRED"
        }
        assert await _references(repo, "projects/archivum") == {
            "page:default:projects/archductor": "INFERRED"
        }
    for slug, text in pages.items():
        assert (env.wiki_dir / f"{slug}.md").read_text(encoding="utf-8") == text


def _write(settings, slug: str, text: str) -> None:
    path = settings.wiki_dir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


async def _indexed_references(slug: str) -> dict[str, str]:
    async with sqlite_mod.get_db() as conn:
        return await _references(KnowledgeRepository(conn), slug)


async def test_a_page_written_before_the_page_it_names_still_links_to_it(env, mock_kuzu_conn):
    """Order of writing must not decide the graph.

    The notes were indexed when neither title existed. Without re-reading them
    when the titles arrive, they stayed unlinked — and while only "Ledger"
    existed, they linked the shorter title nested inside "Ledger Design".
    """
    _write(env, "notes", "# Notes\n\nWe sketched the Ledger Design first.\n")
    await reindex_page("notes", wiki_id="default", settings=env)
    assert await _indexed_references("notes") == {}

    _write(env, "code/ledger/index", "# Ledger\n")
    await reindex_page("code/ledger/index", wiki_id="default", settings=env)
    _write(env, "projects/ledger-design", "# Ledger Design\n")
    await reindex_page("projects/ledger-design", wiki_id="default", settings=env)

    assert await _indexed_references("notes") == {
        "page:default:projects/ledger-design": "INFERRED"
    }


async def test_retitling_a_page_moves_the_references_to_it(env, mock_kuzu_conn):
    _write(env, "projects/a", "# Archfleet\n")
    await reindex_page("projects/a", wiki_id="default", settings=env)
    _write(env, "old-notes", "# Old Notes\n\nArchfleet runs the VMs.\n")
    _write(env, "new-notes", "# New Notes\n\nFleetview runs the VMs.\n")
    await reindex_page("old-notes", wiki_id="default", settings=env)
    await reindex_page("new-notes", wiki_id="default", settings=env)
    assert await _indexed_references("old-notes") == {"page:default:projects/a": "INFERRED"}

    _write(env, "projects/a", "# Fleetview\n")
    await reindex_page("projects/a", wiki_id="default", settings=env)

    assert await _indexed_references("old-notes") == {}
    assert await _indexed_references("new-notes") == {"page:default:projects/a": "INFERRED"}
