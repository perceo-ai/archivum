"""A repository's graph has to become files you own.

Everything else in Archivum ends up as markdown in the vault. Code was the sole
exception — canonical records and a lexical index, no files — so the one part of
a developer's memory that could not be read, edited, linked or exported was the
part about their own work.

Communities come from the deterministic graph audit, so the same repository
always produces the same clusters. Each cluster page leads with a narrative a
model wrote from the extracted symbols; these tests stand a fake model in for
the real one, so they are deterministic and never spawn a CLI.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.code_pages import (
    is_test_path,
    narrative_is_substantive,
    render_community_page,
    repo_folder,
    slugify,
)
from archivum.code_repos import register_repo, run_pending_repo_indexing
from archivum.config import Settings

# Two clusters that barely touch: a geo module and an unrelated retry module.
GEO = (
    "def haversine(lat, lon):\n"
    "    return normalise(lat) + normalise(lon)\n"
    "\n\n"
    "def normalise(value):\n"
    "    return value % 360\n"
)
RETRY = (
    "def with_backoff(fn):\n"
    "    return schedule(fn)\n"
    "\n\n"
    "def schedule(fn):\n"
    "    return fn\n"
)
# A test file that only talks to itself: a cluster made of nothing but tests.
CLOCK_TEST = (
    "def test_tick_advances():\n"
    "    assert tick(1) == 2\n"
    "\n\n"
    "def tick(value):\n"
    "    return value + 1\n"
)

# What the indexer used to write as the whole of a cluster page. It is metadata
# about a cluster, not knowledge about code, and must never land as a page.
OLD_STUB = (
    "Part of [[code/atlas/index|atlas]]. 4 records that the graph found to be "
    "more connected to each other than to the rest of the repository."
)

_ANCHOR = re.compile(r"`([^`\s]+\.\w+:\d+(?:-\d+)?)`")


async def fake_narrator(*, provider: str, model: str, prompt: str, **_: object) -> str:
    """Stands in for the model: prose built only from what the prompt cites."""
    anchors = _ANCHOR.findall(prompt)
    assert anchors, "the prompt must hand the model real file:line anchors"
    first = anchors[0]
    return (
        f"This subsystem groups the code around `{first}` so that callers have one "
        "place to reach for this behaviour instead of repeating it. The entry point "
        f"at `{first}` is where a reader should start, because every other member "
        "of the cluster is reached from it. It exists to keep this concern in one "
        "file rather than spreading it across the repository, and it does not "
        "depend on any other subsystem that the graph can see."
    )


@pytest.fixture(autouse=True)
def _needs_git():
    if shutil.which("git") is None:
        pytest.skip("git not available")


@pytest.fixture
def vault(tmp_path):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
        code_cache_dir=tmp_path / "code-cache",
    )
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    return settings


def make_repo(root: Path, name: str = "atlas", extra: dict[str, str] | None = None) -> Path:
    repo = root / name
    repo.mkdir(parents=True)
    (repo / "geo.py").write_text(GEO, encoding="utf-8")
    (repo / "retry.py").write_text(RETRY, encoding="utf-8")
    for relative, text in (extra or {}).items():
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / relative).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.email=t@example.com", "-c", "user.name=Test",
            "commit", "-q", "-m", "initial",
        ],
        check=True,
    )
    return repo


async def _index(settings, tmp_path, *, narrator=fake_narrator, extra=None):
    await sqlite_mod.init_db(settings)
    await register_repo(path=make_repo(tmp_path, extra=extra), wiki_id="default")
    await _reindex(settings, narrator=narrator)


async def _reindex(settings, *, narrator=fake_narrator):
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
        patch("archivum.code_pages.cli_chat_completion", new=narrator),
    ):
        await run_pending_repo_indexing(settings=settings)


def _cluster_pages(settings) -> list[Path]:
    folder = settings.wiki_dir / "code" / "atlas"
    return sorted(p for p in folder.glob("*.md") if p.name != "index.md")


def _tags(page: Path) -> list[str]:
    match = re.search(r"^tags: \[(.*)\]$", page.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{page.name} should carry tags in its frontmatter"
    return [tag.strip() for tag in match.group(1).split(",")]


async def test_indexing_writes_an_index_page_into_the_vault(vault, tmp_path, mock_kuzu_conn):
    await _index(vault, tmp_path)

    index = vault.wiki_dir / "code" / "atlas" / "index.md"
    assert index.exists(), "a repository should leave a readable page behind"

    body = index.read_text(encoding="utf-8")
    assert "# atlas" in body
    assert "records" in body
    # Provenance is the point: the page must say what was extracted vs inferred.
    assert "extracted" in body.lower()


async def test_each_cluster_becomes_its_own_linked_page(vault, tmp_path, mock_kuzu_conn):
    await _index(vault, tmp_path)

    folder = vault.wiki_dir / "code" / "atlas"
    cluster_pages = [p for p in folder.glob("*.md") if p.name != "index.md"]
    assert cluster_pages, "clusters should each get a page"

    index_body = (folder / "index.md").read_text(encoding="utf-8")
    for page in cluster_pages:
        slug = f"code/atlas/{page.stem}"
        assert f"[[{slug}" in index_body, f"{slug} should be linked from the index"


async def test_cluster_pages_cite_the_file_and_line_they_came_from(vault, tmp_path, mock_kuzu_conn):
    await _index(vault, tmp_path)

    folder = vault.wiki_dir / "code" / "atlas"
    bodies = "\n".join(
        page.read_text(encoding="utf-8") for page in folder.glob("*.md")
    )
    assert "haversine" in bodies
    assert ".py" in bodies, "records should name the file they were read from"


async def test_code_pages_are_real_indexed_pages_not_loose_files(vault, tmp_path, mock_kuzu_conn):
    await _index(vault, tmp_path)

    rows = await sqlite_mod.list_pages("default")
    slugs = {row["slug"] for row in rows}
    assert "code/atlas/index" in slugs, "the page must go through the one indexing path"


async def test_reindexing_an_unchanged_repo_rewrites_the_same_pages(vault, tmp_path, mock_kuzu_conn):
    """Deterministic clustering means no churn when nothing changed."""
    await _index(vault, tmp_path)
    folder = vault.wiki_dir / "code" / "atlas"
    before = {p.name: p.read_text(encoding="utf-8") for p in folder.glob("*.md")}

    await register_repo(path=tmp_path / "atlas", wiki_id="default")
    await _reindex(vault)

    after = {p.name: p.read_text(encoding="utf-8") for p in folder.glob("*.md")}
    assert after == before


def test_folder_and_slug_helpers_are_vault_safe():
    assert repo_folder("My Repo") == "code/my-repo"
    assert slugify("Cluster: retry & backoff") == "cluster-retry-backoff"
    assert slugify("///") == "untitled"


async def test_locations_are_repo_relative_not_absolute_server_paths(vault, tmp_path, mock_kuzu_conn):
    """A page you read should say `geo.py:12-18`, not the server's temp path.

    Citations record where the file was on the machine that indexed it. Printing
    that verbatim leaks the deployment's filesystem layout into your vault and
    buries the only part that matters — which file, which lines.
    """
    await _index(vault, tmp_path)

    bodies = "\n".join(
        page.read_text(encoding="utf-8")
        for page in (vault.wiki_dir / "code" / "atlas").glob("*.md")
    )
    assert str(tmp_path) not in bodies, "absolute host paths must not reach the vault"
    assert "geo.py" in bodies


async def test_line_ranges_read_as_line_numbers(vault, tmp_path, mock_kuzu_conn):
    """`geo.py:1-6`, not `geo.py:1-L6`."""
    import re

    await _index(vault, tmp_path)

    bodies = "\n".join(
        page.read_text(encoding="utf-8")
        for page in (vault.wiki_dir / "code" / "atlas").glob("*.md")
    )
    assert not re.search(r":\d+-L\d+", bodies), "half-stripped line ranges"
    assert re.search(r"\.py:\d+-\d+", bodies), "a location should name its lines"


async def test_repo_metadata_does_not_get_a_cluster_page(vault, tmp_path, mock_kuzu_conn):
    """The repo node and its commit cluster together and say nothing.

    They are bookkeeping, not structure, and a page titled after the repository
    that contains only "this repo, that commit" competes with the real index.
    """
    await _index(vault, tmp_path)

    folder = vault.wiki_dir / "code" / "atlas"
    assert not (folder / "atlas.md").exists()
    assert (folder / "index.md").exists()


async def test_the_index_lists_what_broke_and_what_fixed_it(vault, tmp_path, mock_kuzu_conn):
    """The vault is where you read, so this is where fix memory belongs."""
    from archivum.capture.schema import Conversation, ToolCall, Turn
    from archivum.knowledge.repository import KnowledgeRepository
    from archivum.sessions import record_session_work

    await _index(vault, tmp_path)

    async with sqlite_mod.get_db() as conn:
        await record_session_work(
            KnowledgeRepository(conn),
            conversation=Conversation(
                session_id="s",
                interface="claude_code_import",
                started_at="",
                turns=(
                    Turn(role="user", text="haversine crashes with TypeError: bad operand"),
                    Turn(
                        role="assistant",
                        text="normalise returned a string instead of a number.",
                        tool_calls=(
                            ToolCall(
                                name="Edit",
                                arguments={"file_path": str(tmp_path / "atlas" / "geo.py")},
                                result="ok",
                            ),
                        ),
                    ),
                ),
            ),
            source_id="src-fix",
            wiki_id="default",
        )
        await conn.commit()

    from archivum.code_repos import get_repo
    from archivum.code_pages import write_repo_pages

    repo = await get_repo("repo:default:atlas", wiki_id="default")
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
        patch("archivum.code_pages.cli_chat_completion", new=fake_narrator),
    ):
        await write_repo_pages(repo, settings=vault)

    body = (vault.wiki_dir / "code" / "atlas" / "index.md").read_text(encoding="utf-8")
    assert "TypeError" in body, "a remembered fix should be readable in the vault"
    assert "normalise returned a string" in body, "including what caused it"


async def test_a_repository_with_no_remembered_fixes_says_nothing_about_them(vault, tmp_path, mock_kuzu_conn):
    await _index(vault, tmp_path)

    body = (vault.wiki_dir / "code" / "atlas" / "index.md").read_text(encoding="utf-8")
    assert "What broke before" not in body


# ── Narrative, not metadata ──────────────────────────────────────────────────


async def test_cluster_pages_lead_with_prose_that_cites_file_and_line(vault, tmp_path, mock_kuzu_conn):
    """A cluster page says what the code does, anchored to where it lives."""
    await _index(vault, tmp_path)

    pages = _cluster_pages(vault)
    assert pages
    for page in pages:
        body = page.read_text(encoding="utf-8")
        assert "This subsystem groups the code around" in body
        assert re.search(r"`[\w/.-]+\.py:\d+(-\d+)?`", body), "prose must cite path:line"
        # The deterministic citation sections stay underneath the narrative.
        assert "## What is in here" in body
        assert body.index("This subsystem") < body.index("## What is in here")


async def test_the_prompt_is_built_from_extracted_material(vault, tmp_path, mock_kuzu_conn):
    """Signatures and locations go to the model; nothing it could invent from."""
    prompts: list[str] = []

    async def recording(*, provider, model, prompt, **kwargs):
        prompts.append(prompt)
        return await fake_narrator(provider=provider, model=model, prompt=prompt)

    await _index(vault, tmp_path, narrator=recording)

    joined = "\n".join(prompts)
    assert "def haversine(lat, lon)" in joined, "signatures should reach the prompt"
    assert "geo.py:1-2" in joined, "locations should reach the prompt as path:line"
    assert str(tmp_path) not in joined, "host paths should not reach the model"


def test_a_metadata_only_body_is_rejected_by_the_stub_guard():
    """The old cluster sentence is exactly what must never land as a page."""
    known = {"geo.py:1-2", "geo.py:5-6"}
    assert not narrative_is_substantive(OLD_STUB, known_locations=known)
    assert not narrative_is_substantive("", known_locations=known)
    assert not narrative_is_substantive("   \n ", known_locations=known)


def test_a_narrative_citing_lines_it_was_never_shown_is_rejected():
    """Long, confident prose with an invented anchor is worse than nothing."""
    known = {"geo.py:1-2", "geo.py:5-6"}
    invented = (
        "This subsystem computes great-circle distances. " * 10
        + "Start at `geo.py:1-2`, then read the cache in `cache.py:40-80`."
    )
    assert not narrative_is_substantive(invented, known_locations=known)
    honest = invented.replace("`cache.py:40-80`", "`geo.py:5-6`")
    assert narrative_is_substantive(honest, known_locations=known)


def test_render_refuses_to_produce_a_page_from_a_stub(vault):
    """The guard sits in the render path, not beside it."""
    from archivum.knowledge.graph_audit import Community
    from archivum.knowledge.models import Citation, KnowledgeObject

    member = KnowledgeObject(
        id="sym:geo:haversine",
        kind="symbol",
        label="haversine",
        scope="repo:default:atlas",
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=[
            Citation(
                source_id="/r/geo.py",
                chunk_id="/r/geo.py",
                span_start=None,
                span_end=None,
                quote="L1-L2",
            )
        ],
        properties={"signature": "def haversine(lat, lon)", "summary": ""},
    )
    community = Community(id=member.id, label="geo", member_ids=(member.id,))

    def render(narrative: str):
        return render_community_page(
            community,
            repo_name="atlas",
            objects_by_id={member.id: member},
            edges=[],
            repo_root="/r",
            narrative=narrative,
        )

    assert render(OLD_STUB) is None
    assert render("") is None
    # The same cluster with a real account does render, so the None above is
    # the guard speaking and not some other failure.
    real = (
        "Geodesy helpers live here, so distance maths has one home. "
        "The entry point is haversine at `geo.py:1-2`, which takes a latitude and "
        "a longitude and combines them after normalising each one. It exists so "
        "that callers never reimplement the formula, and nothing else in the "
        "repository reaches into it beyond calling that single function directly."
    )
    page = render(real)
    assert page is not None and "haversine at `geo.py:1-2`" in page


async def test_a_failed_model_writes_no_cluster_pages(vault, tmp_path, mock_kuzu_conn):
    """A failed model leaves nothing — and the count says so honestly."""
    from archivum.code_repos import get_repo
    from archivum.llm.cli_client import CliModelError

    async def broken(**_):
        raise CliModelError("model unavailable")

    await _index(vault, tmp_path, narrator=broken)

    assert _cluster_pages(vault) == [], "no narrative means no page, not a stub"
    repo = await get_repo("repo:default:atlas", wiki_id="default")
    assert repo is not None and repo.pages == 1, "only the index landed"

    index = (vault.wiki_dir / "code" / "atlas" / "index.md").read_text(encoding="utf-8")
    assert "not written up" in index.lower(), "the index should say what was skipped"
    assert "[[code/atlas/geo" not in index, "a skipped cluster must not be linked"


async def test_a_stub_reply_from_the_model_is_not_written(vault, tmp_path, mock_kuzu_conn):
    async def stubby(**_):
        return OLD_STUB

    await _index(vault, tmp_path, narrator=stubby)

    assert _cluster_pages(vault) == []


async def test_reindexing_reuses_the_narrative_instead_of_asking_again(vault, tmp_path, mock_kuzu_conn):
    """Unchanged code costs no model calls and produces no churn."""
    await _index(vault, tmp_path)
    before = {p.name: p.read_text(encoding="utf-8") for p in _cluster_pages(vault)}

    calls = AsyncMock(side_effect=AssertionError("unchanged code must not re-ask the model"))
    await register_repo(path=tmp_path / "atlas", wiki_id="default")
    await _reindex(vault, narrator=calls)

    after = {p.name: p.read_text(encoding="utf-8") for p in _cluster_pages(vault)}
    assert after == before
    calls.assert_not_called()


# ── Tags that say something ──────────────────────────────────────────────────


async def test_unrelated_clusters_get_different_tags(vault, tmp_path, mock_kuzu_conn):
    await _index(vault, tmp_path)

    pages = _cluster_pages(vault)
    assert len(pages) >= 2, "the fixture has two unrelated clusters"
    tag_sets = [frozenset(_tags(page)) for page in pages]
    for tags in tag_sets:
        assert tags != {"code", "cluster"}
        assert "python" in tags, "the language is read from the members' files"
    assert len(set(tag_sets)) == len(tag_sets), f"tag sets should differ: {tag_sets}"

    geo = next(tags for page, tags in zip(pages, tag_sets) if "haversine" in page.read_text())
    retry = next(tags for page, tags in zip(pages, tag_sets) if "with_backoff" in page.read_text())
    assert geo - retry and retry - geo


# ── Tests are not subsystems ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "path",
    [
        "tests/test_geo.py",
        "test_geo.py",
        "geo_test.py",
        "conftest.py",
        "pkg/tests/helpers.py",
        "src/__tests__/icon.tsx",
        "src/icon.test.tsx",
        "src/newChatContext.test.ts",
        "src/api.spec.js",
        "internal/clock_test.go",
        "spec/models/user_spec.rb",
    ],
)
def test_test_paths_are_recognised(path):
    assert is_test_path(path)


@pytest.mark.parametrize(
    "path",
    ["geo.py", "src/testing_utils_contest.py", "src/latest.py", "src/attestation.ts", "contest.py"],
)
def test_ordinary_paths_are_not_tests(path):
    assert not is_test_path(path)


async def test_a_cluster_made_only_of_tests_gets_no_page(vault, tmp_path, mock_kuzu_conn):
    """`icon.test` is not a subsystem; it must not compete with the code it tests."""
    await _index(vault, tmp_path, extra={"test_clock.py": CLOCK_TEST})

    bodies = "\n".join(p.read_text(encoding="utf-8") for p in _cluster_pages(vault))
    assert "test_tick_advances" not in bodies
    assert "haversine" in bodies, "real code still gets its page"

    index = (vault.wiki_dir / "code" / "atlas" / "index.md").read_text(encoding="utf-8")
    assert "test_clock" in index, "the index still accounts for the test cluster"
    assert "[[code/atlas/test-clock" not in index


# ── QA round 1: stale pages, reversed ranges, the prompt window ──────────────

# What `main` used to write for a cluster: no narrative, the old footer.
LEGACY_PAGE = (
    "# test_clock\n\n"
    + OLD_STUB
    + "\n\n## What is in here\n\n- **tick** (symbol) — `test_clock.py:5-6`\n\n---\n\n"
    "Generated from the code graph. Edit freely — your words are kept, and "
    "reindexing will not overwrite a page you have taken over.\n"
)
HAND_WRITTEN = "# Notes\n\nMy own notes about atlas. Nothing generated here.\n"


async def _write_page(settings, slug: str, body: str, *, authored_by: str = "user") -> None:
    """A page on disk and in the page table, the way any vault write lands."""
    from archivum.indexing import reindex_page

    path = settings.wiki_dir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
    ):
        await reindex_page(
            slug,
            wiki_id="default",
            settings=settings,
            force=True,
            authored_by=authored_by,
            distill=False,
        )


async def _reindex_watching_deletes(settings, *, narrator=fake_narrator):
    """Reindex, recording what was removed from the vector and graph stores."""
    qdrant_delete = AsyncMock()
    graph_delete = AsyncMock()
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
        patch("archivum.indexing.qdrant.delete_page", new=qdrant_delete),
        patch("archivum.indexing.graph.delete_page_node", new=graph_delete),
        patch("archivum.code_pages.cli_chat_completion", new=narrator),
    ):
        await run_pending_repo_indexing(settings=settings)
    return (
        {call.args[0] for call in qdrant_delete.await_args_list},
        {call.args[0] for call in graph_delete.await_args_list},
    )


def _commit_all(repo: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(
        [
            "git", "-C", str(repo),
            "-c", "user.email=t@example.com", "-c", "user.name=Test",
            "commit", "-q", "-m", message,
        ],
        check=True,
    )


async def test_a_rejected_narrative_removes_the_page_it_used_to_have(vault, tmp_path, mock_kuzu_conn):
    """The index saying "not written up" while search serves the old body is a lie."""
    await _index(vault, tmp_path)
    folder = vault.wiki_dir / "code" / "atlas"
    assert (folder / "geo.md").exists(), "precondition: geo had a page"
    await _write_page(vault, "code/atlas/notes", HAND_WRITTEN)

    # The code changes, so the stored narrative no longer matches, and the
    # model's new account is a stub the guard rejects.
    repo = tmp_path / "atlas"
    (repo / "geo.py").write_text(GEO + "\n\ndef bearing(a, b):\n    return normalise(a - b)\n")
    _commit_all(repo, "add bearing")

    async def stubby(**_):
        return OLD_STUB

    await register_repo(path=repo, wiki_id="default")
    qdrant_deleted, graph_deleted = await _reindex_watching_deletes(vault, narrator=stubby)

    assert not (folder / "geo.md").exists(), "stale page must leave the disk"
    assert await sqlite_mod.get_page("code/atlas/geo", "default") is None, "and the page table"
    assert "code/atlas/geo" in qdrant_deleted, "and the vectors"
    assert "code/atlas/geo" in graph_deleted, "and the graph"

    index = (folder / "index.md").read_text(encoding="utf-8")
    assert "not written up" in index.lower()

    assert (folder / "notes.md").read_text(encoding="utf-8") == HAND_WRITTEN
    assert await sqlite_mod.get_page("code/atlas/notes", "default") is not None
    assert "code/atlas/notes" not in qdrant_deleted | graph_deleted


async def test_a_cluster_reclassified_as_tests_loses_its_old_page(vault, tmp_path, mock_kuzu_conn):
    """The production `icon.test` pages: written before tests were recognised."""
    await sqlite_mod.init_db(vault)
    await _write_page(vault, "code/atlas/test-clock", LEGACY_PAGE, authored_by="agent")
    await _write_page(vault, "code/atlas/notes", HAND_WRITTEN)
    assert await sqlite_mod.get_page("code/atlas/test-clock", "default") is not None

    await register_repo(
        path=make_repo(tmp_path, extra={"test_clock.py": CLOCK_TEST}), wiki_id="default"
    )
    qdrant_deleted, graph_deleted = await _reindex_watching_deletes(vault)

    folder = vault.wiki_dir / "code" / "atlas"
    assert not (folder / "test-clock.md").exists()
    assert await sqlite_mod.get_page("code/atlas/test-clock", "default") is None
    assert "code/atlas/test-clock" in qdrant_deleted
    assert "code/atlas/test-clock" in graph_deleted
    assert "test_clock" in (folder / "index.md").read_text(encoding="utf-8")

    assert (folder / "notes.md").read_text(encoding="utf-8") == HAND_WRITTEN
    assert await sqlite_mod.get_page("code/atlas/notes", "default") is not None
    assert "code/atlas/notes" not in qdrant_deleted | graph_deleted
    assert (folder / "geo.md").exists(), "real code keeps its page"


async def test_a_page_someone_else_wrote_at_a_cluster_slug_is_left_alone(vault, tmp_path, mock_kuzu_conn):
    """Only this indexer's own pages are ever removed."""
    await sqlite_mod.init_db(vault)
    mine = "# test_clock\n\nWhat I learned about the clock tests.\n"
    await _write_page(vault, "code/atlas/test-clock", mine)

    await register_repo(
        path=make_repo(tmp_path, extra={"test_clock.py": CLOCK_TEST}), wiki_id="default"
    )
    qdrant_deleted, graph_deleted = await _reindex_watching_deletes(vault)

    page = vault.wiki_dir / "code" / "atlas" / "test-clock.md"
    assert page.read_text(encoding="utf-8") == mine
    assert await sqlite_mod.get_page("code/atlas/test-clock", "default") is not None
    assert "code/atlas/test-clock" not in qdrant_deleted | graph_deleted


# A page the indexer generated, under each marker it has ever written.
NARRATIVE_PAGE = (
    "# test_clock\n\nPart of [[code/atlas/index|atlas]].\n\n"
    "<!-- archivum:narrative 0123456789abcdef -->\n"
    + "The clock helpers advance a counter one tick at a time; start at "
    "`test_clock.py:5-6`."
    + "\n<!-- /archivum:narrative -->\n\n---\n\n"
    "The overview was written by a model from the records listed here and "
    "cites only them; the lists come from the code graph directly.\n"
)
HUMAN_NOTES = "\n## My notes\n\nFLAKY ON CI: tick() races the scheduler — do not delete.\n"


@pytest.mark.parametrize("edit", ["resaved", "unswept"])
@pytest.mark.parametrize("path", ["rejected", "test-only"])
@pytest.mark.parametrize("marker", ["legacy-footer", "narrative-block"])
async def test_a_generated_page_someone_has_edited_is_never_retired(
    vault, tmp_path, mock_kuzu_conn, marker, path, edit
):
    """The footer invites edits; retiring the page would delete them.

    `resaved` is an edit the vault watcher has already indexed (the row says
    `user`); `unswept` is one it has not reached yet (the row still says
    `agent`, but the file is no longer what the indexer wrote).
    """
    folder = vault.wiki_dir / "code" / "atlas"
    if path == "rejected":
        slug = "code/atlas/geo"
        await _index(vault, tmp_path)  # the indexer writes geo.md, as the agent
        if marker == "legacy-footer":
            body = LEGACY_PAGE.replace("# test_clock", "# geo")
            await _write_page(vault, slug, body, authored_by="agent")
    else:
        slug = "code/atlas/test-clock"
        await sqlite_mod.init_db(vault)
        body = LEGACY_PAGE if marker == "legacy-footer" else NARRATIVE_PAGE
        await _write_page(vault, slug, body, authored_by="agent")

    page = vault.wiki_dir / f"{slug}.md"
    edited = page.read_text(encoding="utf-8") + HUMAN_NOTES
    if edit == "resaved":
        await _write_page(vault, slug, edited)  # authored_by="user"
        row = await sqlite_mod.get_page(slug, "default")
        assert row is not None and row["authored_by"] == "user"
    else:
        page.write_text(edited, encoding="utf-8")
        row = await sqlite_mod.get_page(slug, "default")
        assert row is not None and row["authored_by"] == "agent"
    await _write_page(vault, "code/atlas/notes", HAND_WRITTEN)

    if path == "rejected":
        repo = tmp_path / "atlas"
        (repo / "geo.py").write_text(GEO + "\n\ndef bearing(a, b):\n    return normalise(a - b)\n")
        _commit_all(repo, "add bearing")

        async def stubby(**_):
            return OLD_STUB

        await register_repo(path=repo, wiki_id="default")
        deleted = await _reindex_watching_deletes(vault, narrator=stubby)
        index = (folder / "index.md").read_text(encoding="utf-8")
        assert "geo — " in index and "not written up" in index.lower(), "precondition: rejected"
    else:
        await register_repo(
            path=make_repo(tmp_path, extra={"test_clock.py": CLOCK_TEST}), wiki_id="default"
        )
        deleted = await _reindex_watching_deletes(vault)
        assert "## Tests" in (folder / "index.md").read_text(encoding="utf-8"), "precondition: test-only"

    qdrant_deleted, graph_deleted = deleted
    assert page.exists(), "the edited page stays on disk"
    assert "FLAKY ON CI" in page.read_text(encoding="utf-8"), "with the person's notes in it"
    assert slug not in qdrant_deleted | graph_deleted, "and is not among what was deleted"
    assert await sqlite_mod.get_page(slug, "default") is not None, "and keeps its page row"
    assert (folder / "notes.md").read_text(encoding="utf-8") == HAND_WRITTEN


async def test_a_vault_rebuild_does_not_stop_stale_pages_being_retired(vault, tmp_path, mock_kuzu_conn):
    """Rebuild, then reject: the untouched generated page is still retired."""
    from archivum.indexing import reconcile_vault

    await _index(vault, tmp_path)
    folder = vault.wiki_dir / "code" / "atlas"
    assert (folder / "geo.md").exists(), "precondition: geo had a page"

    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
    ):
        await reconcile_vault(wiki_id="default", settings=vault, force=True)
    row = await sqlite_mod.get_page("code/atlas/geo", "default")
    assert row is not None and row["authored_by"] == "agent"

    repo = tmp_path / "atlas"
    (repo / "geo.py").write_text(GEO + "\n\ndef bearing(a, b):\n    return normalise(a - b)\n")
    _commit_all(repo, "add bearing")

    async def stubby(**_):
        return OLD_STUB

    await register_repo(path=repo, wiki_id="default")
    qdrant_deleted, graph_deleted = await _reindex_watching_deletes(vault, narrator=stubby)

    assert not (folder / "geo.md").exists()
    assert await sqlite_mod.get_page("code/atlas/geo", "default") is None
    assert "code/atlas/geo" in qdrant_deleted and "code/atlas/geo" in graph_deleted


def test_a_reversed_line_range_is_not_a_citation():
    """`geo.py:999-1` passed both bound checks independently."""
    known = {"geo.py:1-2"}
    prose = "This subsystem computes great-circle distances between points. " * 8
    assert not narrative_is_substantive(prose + "See `geo.py:999-1`.", known_locations=known)
    assert not narrative_is_substantive(prose + "See `geo.py:0-1`.", known_locations=known)
    assert narrative_is_substantive(prose + "See `geo.py:1-2`.", known_locations=known)


def _big_cluster(size: int = 45):
    """A cluster larger than the prompt window: sym_00 … sym_44 in big.py."""
    from archivum.knowledge.graph_audit import Community
    from archivum.knowledge.models import Citation, KnowledgeObject

    members = {}
    for index in range(size):
        start = index * 10 + 1
        member = KnowledgeObject(
            id=f"sym:big:sym_{index:02d}",
            kind="symbol",
            label=f"sym_{index:02d}",
            scope="repo:default:atlas",
            confidence=1.0,
            extraction_method="EXTRACTED",
            citations=[
                Citation(
                    source_id="/r/big.py",
                    chunk_id="/r/big.py",
                    span_start=None,
                    span_end=None,
                    quote=f"L{start}-L{start + 4}",
                )
            ],
            properties={"signature": f"def sym_{index:02d}()", "summary": ""},
        )
        members[member.id] = member
    community = Community(id="sym:big:sym_00", label="big", member_ids=tuple(sorted(members)))
    return community, members


def _narrative_citing(anchor: str) -> str:
    return (
        "This subsystem gathers the numbered helpers of the big module so they "
        "share one home rather than scattering across the repository. A reader "
        f"should start at `{anchor}`, which is the helper the rest lean on, and "
        "then follow the calls outward; nothing outside this module is reached "
        "from here, so it stands alone in the graph as far as it can tell."
    )


INSIDE_WINDOW = "big.py:51-55"  # sym_05, inside the 40 the model is shown
OUTSIDE_WINDOW = "big.py:421-425"  # sym_42, a real member it is never shown


def test_render_rejects_citations_to_members_the_prompt_never_showed():
    import archivum.code_pages as code_pages

    assert code_pages.MAX_MEMBERS_IN_PROMPT < 45 <= code_pages.MAX_MEMBERS_PER_PAGE
    community, members = _big_cluster()

    def render(narrative: str):
        return render_community_page(
            community,
            repo_name="atlas",
            objects_by_id=members,
            edges=[],
            repo_root="/r",
            narrative=narrative,
        )

    assert render(_narrative_citing(OUTSIDE_WINDOW)) is None
    assert render(_narrative_citing(INSIDE_WINDOW)) is not None


async def test_narration_rejects_citations_to_members_the_prompt_never_showed(vault):
    from archivum.code_pages import narrate_communities

    community, members = _big_cluster()
    prompts: list[str] = []

    async def run(anchor: str):
        async def narrator(*, provider, model, prompt, **_):
            prompts.append(prompt)
            return _narrative_citing(anchor)

        with patch("archivum.code_pages.cli_chat_completion", new=narrator):
            result = await narrate_communities(
                [community],
                repo_name="atlas",
                objects_by_id=members,
                edges=[],
                community_of={},
                repo_root="/r",
                settings=vault,
            )
        return result[community.id]

    outside = await run(OUTSIDE_WINDOW)
    assert outside.text == "" and outside.reason
    assert f"`{OUTSIDE_WINDOW}`" not in prompts[-1], "the member really was outside the window"

    inside = await run(INSIDE_WINDOW)
    assert inside.text and not inside.reason
    assert f"`{INSIDE_WINDOW}`" in prompts[-1]


# Two clusters joined by a real call and a real import: retry reaches into geo.
LINKED_GEO = (
    "def haversine(lat, lon):\n"
    "    return normalise(lat) + bearing(lon)\n"
    "\n\n"
    "def bearing(value):\n"
    "    return normalise(value) * 2\n"
    "\n\n"
    "def normalise(value):\n"
    "    return value % 360\n"
)
LINKED_RETRY = (
    "from geo import haversine\n"
    "\n\n"
    "def with_backoff(fn):\n"
    "    haversine(1, 2)\n"
    "    return schedule(fn) + jitter(fn)\n"
    "\n\n"
    "def schedule(fn):\n"
    "    return jitter(fn)\n"
    "\n\n"
    "def jitter(fn):\n"
    "    return fn\n"
)
LINKED = {"geo.py": LINKED_GEO, "retry.py": LINKED_RETRY}


async def _lint(settings) -> dict:
    from archivum.linting import analyze_wiki_pages

    return analyze_wiki_pages(await sqlite_mod.list_page_contents("default"))


async def test_sibling_clusters_link_to_the_pages_they_call(vault, tmp_path, mock_kuzu_conn):
    """A call between two subsystems is a link between their two pages.

    Each page only ever linked up to the index, so the pages a reader most
    wants to move between — the caller's and the callee's — had no path
    between them except back through the repository's front page.
    """
    await _index(vault, tmp_path, extra=LINKED)

    folder = vault.wiki_dir / "code" / "atlas"
    geo = (folder / "geo.md").read_text(encoding="utf-8")
    retry = (folder / "retry.md").read_text(encoding="utf-8")

    assert "with_backoff → *calls* → [[code/atlas/geo|haversine]]" in retry
    assert "[[code/atlas/retry|with_backoff]] → *calls* → haversine" in geo
    assert "[[code/atlas/geo" not in geo, "a page must not link to itself"

    lint = await _lint(vault)
    assert lint["broken_wikilinks"] == []
    assert lint["orphan_pages"] == []


async def test_an_edge_to_a_cluster_without_a_page_stays_prose(vault, tmp_path, mock_kuzu_conn):
    """A link to a page that was never written is a broken link, not an edge."""

    async def no_page_for_retry(*, prompt: str, **kwargs):
        if _ANCHOR.findall(prompt)[0].startswith("retry.py"):
            return "retry"
        return await fake_narrator(prompt=prompt, **kwargs)

    await _index(vault, tmp_path, extra=LINKED, narrator=no_page_for_retry)

    folder = vault.wiki_dir / "code" / "atlas"
    assert not (folder / "retry.md").exists()
    geo = (folder / "geo.md").read_text(encoding="utf-8")
    assert "with_backoff → *calls* → haversine" in geo
    assert "[[code/atlas/retry" not in geo
    assert (await _lint(vault))["broken_wikilinks"] == []


async def test_linked_clusters_are_connected_in_the_canonical_graph(vault, tmp_path, mock_kuzu_conn):
    """The same link has to reach the graph `graph_shortest_path` reads.

    Every page also hangs off the owner root, and the path search is
    undirected, so the root is left out: a path through it says only that
    both pages have an owner.
    """
    from archivum.knowledge.graph_audit import load_graph, shortest_path
    from archivum.knowledge.personal_root import SELF_ID
    from archivum.knowledge.repository import KnowledgeRepository

    await _index(vault, tmp_path, extra=LINKED)

    async with sqlite_mod.get_db() as conn:
        nodes, edges = await load_graph(KnowledgeRepository(conn), scope="wiki:default")
    nodes = [node for node in nodes if node.id != SELF_ID]
    edges = [edge for edge in edges if SELF_ID not in (edge.src_id, edge.dst_id)]

    path = shortest_path(
        nodes, edges, source="page:default:code/atlas/retry", target="page:default:code/atlas/geo"
    )
    assert path.found, path.reason
    assert [step.relation for step in path.steps] == ["references"]
    assert (await _lint(vault))["orphan_pages"] == []


# ── Paths with brackets, spaces, parentheses and plus signs ──────────────────

ROUTE_PATH = "app/[slug]/My Page.tsx"
ROUTE_ANCHOR = f"{ROUTE_PATH}:10-20"


def _route_cluster():
    """One member in a Next.js-style route folder, cited the way the indexer cites it."""
    from archivum.knowledge.graph_audit import Community
    from archivum.knowledge.models import Citation, KnowledgeObject

    member = KnowledgeObject(
        id="sym:route:Page",
        kind="symbol",
        label="Page",
        scope="repo:default:atlas",
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=[
            Citation(
                source_id=f"/r/{ROUTE_PATH}",
                chunk_id=f"/r/{ROUTE_PATH}",
                span_start=None,
                span_end=None,
                quote="L10-L20",
            )
        ],
        properties={"signature": "export default function Page({ params })", "summary": ""},
    )
    community = Community(id=member.id, label="page", member_ids=(member.id,))
    return community, {member.id: member}


def _route_narrative(anchor: str) -> str:
    return (
        "This subsystem renders one dynamic route of the web app, so a page "
        "for each slug is produced by the same component instead of a file per "
        f"page. The entry point is the Page component at `{anchor}`, which "
        "receives the route parameters and renders the content for that slug. "
        "It stands alone: the graph shows no edge from it to any other "
        "subsystem in the repository."
    )


def test_a_path_with_brackets_and_spaces_keeps_its_page():
    """Greptile: `app/[slug]/page.tsx` fell out of the allowed set entirely."""
    import archivum.code_pages as code_pages

    community, members = _route_cluster()
    listed = list(members.values())

    prompt = code_pages._instruction(
        community, repo_name="atlas", members=listed, neighbours=[], repo_root="/r"
    )
    assert f"`{ROUTE_ANCHOR}`" in prompt, "the model is offered the location"

    allowed = code_pages._allowed_locations(listed, repo_root="/r")
    assert allowed == {ROUTE_ANCHOR}
    assert code_pages._spans(allowed) == {ROUTE_PATH: [(10, 20)]}, "and the guard keeps it"

    narrative = _route_narrative(ROUTE_ANCHOR)
    assert narrative_is_substantive(narrative, known_locations=allowed)

    page = render_community_page(
        community,
        repo_name="atlas",
        objects_by_id=members,
        edges=[],
        repo_root="/r",
        narrative=narrative,
    )
    assert page is not None and f"`{ROUTE_ANCHOR}`" in page


@pytest.mark.parametrize(
    "cited",
    [
        "app/[other]/Other Page.tsx:10-20",  # a bracketed, spaced path never offered
        f"{ROUTE_PATH}:30-40",  # the offered path, lines it was not shown
        "app/(group)/c++ notes.tsx:10-20",  # parentheses and plus, never offered
    ],
)
def test_unusual_paths_still_need_provenance(cited):
    """Accepting more characters must not mean accepting more claims."""
    allowed = {ROUTE_ANCHOR}
    assert not narrative_is_substantive(_route_narrative(cited), known_locations=allowed)


def test_a_bare_invented_citation_beside_a_real_one_is_still_rejected():
    """Citations are recognised outside backticks too, and checked the same."""
    known = {"geo.py:1-2"}
    prose = "This subsystem computes great-circle distances between points. " * 8
    assert narrative_is_substantive(prose + "Start at `geo.py:1-2`.", known_locations=known)
    assert not narrative_is_substantive(
        prose + "Start at `geo.py:1-2`, then read cache.py:40-80 for the cache.",
        known_locations=known,
    )
