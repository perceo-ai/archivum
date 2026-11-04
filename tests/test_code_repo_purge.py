"""A repository's debris can be reclaimed, and only its own.

`forget` drops the register row and deliberately keeps the canonical code
records, reasoning that they are memory of work that happened. That reasoning
does not survive a repository whose ingest never finished: what it leaves is
unreachable, because retrieval finds code through the register and the register
entry is gone.

A live vault reached 21 GB that way — 192,704 orphaned symbol objects from
repositories whose own rows still read zero nodes — with nothing in the product
able to reclaim any of it.
"""

# ruff: noqa: F811 - `vault` is an imported fixture, requested by parameter name.

from __future__ import annotations

import aiosqlite
import archivum.db.sqlite as sqlite_mod
import pytest
from archivum.archgraph.lexical import build_lexical_index, trigram_candidates
from archivum.code_repos import (
    init_repo_schema,
    orphan_repo_scopes,
    purge_repo_scope,
)
from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema

from test_code_pages import vault  # noqa: F401


def _symbol(object_id: str, scope: str) -> KnowledgeObject:
    return KnowledgeObject(
        id=object_id,
        kind="symbol",
        label=object_id,
        scope=scope,
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=[
            Citation(
                source_id=f"src:{object_id}",
                chunk_id=f"chunk:{object_id}",
                span_start=None,
                span_end=None,
                quote=object_id,
            )
        ],
        properties={},
    )


async def _seed(vault, scopes: dict[str, list[str]]) -> None:  # noqa: F811
    await sqlite_mod.init_db(vault)
    async with sqlite_mod.get_db() as conn:
        await init_knowledge_schema(conn)
        await init_repo_schema(conn)
        repo = KnowledgeRepository(conn)
        for scope, ids in scopes.items():
            for object_id in ids:
                await repo.upsert_object(_symbol(object_id, scope))
            await build_lexical_index(
                conn, [(object_id, object_id) for object_id in ids], scope=scope
            )
        await conn.commit()


async def _objects_in(scope: str) -> list[str]:
    async with sqlite_mod.get_db() as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT id FROM knowledge_objects WHERE scope=?", (scope,)
        ) as cursor:
            return [row["id"] for row in await cursor.fetchall()]


async def _citation_count() -> int:
    async with sqlite_mod.get_db() as conn:
        async with conn.execute("SELECT COUNT(*) FROM knowledge_citations") as cursor:
            return (await cursor.fetchone())[0]


@pytest.fixture(autouse=True)
def _settings(vault, monkeypatch):  # noqa: F811
    monkeypatch.setattr("archivum.code_repos.get_settings", lambda: vault)
    return vault


async def test_purge_removes_a_scope_and_leaves_its_neighbour_intact(vault):  # noqa: F811
    await _seed(
        vault,
        {
            "repo:default:junk": ["junk:a", "junk:b"],
            "repo:default:keep": ["keep:a"],
        },
    )
    before = await _citation_count()
    assert before == 3

    removed = await purge_repo_scope("repo:default:junk", wiki_id="default")

    assert removed["knowledge_objects"] == 2
    assert await _objects_in("repo:default:junk") == []
    # The point of a scoped purge: the other repository is untouched.
    assert await _objects_in("repo:default:keep") == ["keep:a"]
    assert await _citation_count() == 1, "citations must go with their objects"


async def test_purge_clears_only_its_own_lexical_rows(vault):  # noqa: F811
    await _seed(
        vault,
        {
            "repo:default:junk": ["junk:retry"],
            "repo:default:keep": ["keep:parser"],
        },
    )

    await purge_repo_scope("repo:default:junk", wiki_id="default")

    async with sqlite_mod.get_db() as conn:
        assert await trigram_candidates(conn, "retry", scope="repo:default:junk") == set()
        assert await trigram_candidates(
            conn, "parser", scope="repo:default:keep"
        ) == {"keep:parser"}


async def test_a_scope_with_no_register_row_is_reported_as_an_orphan(vault):  # noqa: F811
    await _seed(vault, {"repo:default:ghost": ["ghost:a"]})

    # Nothing registered it, so retrieval can never reach it: it is pure cost.
    assert await orphan_repo_scopes(wiki_id="default") == ["repo:default:ghost"]

    await purge_repo_scope("repo:default:ghost", wiki_id="default")

    assert await orphan_repo_scopes(wiki_id="default") == []


async def test_purge_deletes_the_page_files_not_just_their_rows(vault):  # noqa: F811
    """Markdown is the source of truth, so dropping rows accomplishes nothing.

    Observed on the deploy: a purge removed 35 page rows, the vault watcher
    found the files still on disk, and the backend spent its next startup
    distilling all 35 pages of the repository that had just been deleted.
    """
    await _seed(vault, {"repo:default:junk": ["junk:a"]})
    page_dir = vault.wiki_dir / "code" / "junk"
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "index.md").write_text("# junk\n", encoding="utf-8")
    keep = vault.wiki_dir / "projects"
    keep.mkdir(parents=True, exist_ok=True)
    (keep / "real.md").write_text("# real\n", encoding="utf-8")

    await purge_repo_scope("repo:default:junk", wiki_id="default")

    assert not page_dir.exists(), "the generated markdown must go with the rows"
    assert (keep / "real.md").exists(), "hand-written pages are not ours to delete"


async def test_purge_removes_the_codegraph_asset_registered_at_wiki_scope(vault):  # noqa: F811
    """The codegraph record names its repo in its id, not in its scope.

    So the scope-matched deletes miss it, and a purge left behind an asset and
    a knowledge object describing a repository that no longer existed.
    """
    await _seed(vault, {"repo:default:junk": ["junk:a"]})
    async with sqlite_mod.get_db() as conn:
        await init_knowledge_schema(conn)
        repo = KnowledgeRepository(conn)
        asset = _symbol("codegraph:repo:default:junk", "wiki:default")
        await repo.upsert_object(asset)
        await conn.execute(
            "INSERT INTO memory_assets (id, wiki_id, asset_type, scope, name, status) "
            "VALUES (?, 'default', 'codegraph', 'wiki:default', ?, 'active')",
            ("codegraph:repo:default:junk", "Code graph — repo:default:junk"),
        )
        await conn.commit()

    await purge_repo_scope("repo:default:junk", wiki_id="default")

    async with sqlite_mod.get_db() as conn:
        async with conn.execute(
            "SELECT COUNT(*) FROM memory_assets WHERE id=?",
            ("codegraph:repo:default:junk",),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0
        async with conn.execute(
            "SELECT COUNT(*) FROM knowledge_objects WHERE id=?",
            ("codegraph:repo:default:junk",),
        ) as cursor:
            assert (await cursor.fetchone())[0] == 0


async def test_purging_an_unknown_scope_is_harmless(vault):  # noqa: F811
    await _seed(vault, {"repo:default:keep": ["keep:a"]})

    removed = await purge_repo_scope("repo:default:never-existed", wiki_id="default")

    assert all(count == 0 for count in removed.values()), removed
    assert await _objects_in("repo:default:keep") == ["keep:a"]


async def test_purge_refuses_a_scope_outside_this_wiki(vault):  # noqa: F811
    """Every delete filters on `scope` alone, so the caller must not choose it.

    `purge-repo personal` would have taken a vault's personal sources, and
    another tenant's `repo:other:x` its code — leaving their register row
    behind to claim the repository was still there.
    """
    from archivum.code_repos import RepoError

    await _seed(vault, {"repo:default:keep": ["keep:a"]})

    for hostile in (
        "personal",
        "wiki:default",
        "repo:other:theirs",
        "repo:default:",
        "repo:default:a:b",
        "",
    ):
        with pytest.raises(RepoError):
            await purge_repo_scope(hostile, wiki_id="default")

    # Nothing was touched by any of those attempts.
    assert await _objects_in("repo:default:keep") == ["keep:a"]


async def test_orphan_listing_stays_inside_this_wiki(vault):  # noqa: F811
    """Listing every wiki's code scopes against one wiki's register reported
    another tenant's live repository as an orphan — an invitation to purge
    something in use."""
    await _seed(
        vault,
        {"repo:default:ghost": ["ghost:a"], "repo:other:live": ["live:a"]},
    )

    assert await orphan_repo_scopes(wiki_id="default") == ["repo:default:ghost"]
