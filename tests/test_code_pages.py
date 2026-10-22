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
