"""The pre-#71 indexer left content-free stub pages behind; purge exactly those.

The audit found 35 of them under `code/nixos`: 34 cluster pages and one index,
all written by the old cluster-metadata template. The fixture here is that shape
and that count, plus the cases the purge must refuse — a page in the folder that
someone has changed, and real pages outside `code/` — so "35" is a number these
tests demonstrate rather than assume.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import archivum.db.sqlite as sqlite_mod
import pytest
from archivum.config import Settings

PREFIX = "code/nixos"
CLUSTER_COUNT = 34
WEIRD = "code/nixos/weird"

# Real, hand-authored pages that live nowhere near code/. They must never be
# read, matched or deleted, whatever prefix the purge is pointed at.
HAND_AUTHORED = {
    "projects/perceo/archductor/archductor": (
        "# Archductor\n\nPhone pairing works by showing a QR code on the desktop "
        "app that the phone scans; the code carries a one-time key.\n"
    ),
    "projects/cad-repair-system": (
        "# CAD repair system\n\nRepairs broken STEP files by re-stitching faces "
        "that share an edge within tolerance.\n"
    ),
    "daily/2026-10-22": "# 2026-10-22\n\n- Audited code/ namespaces; found 35 stubs under code/nixos.\n",
}


def legacy_cluster_body(label: str, members: int, repo_name: str = "nixos") -> str:
    """The pre-#71 `render_community_page`, verbatim in the part that matters."""
    plural = "s" if members != 1 else ""
    bullets = "\n".join(f"- **member_{i}** (function) — `src/m{i}.py:{i + 1}`" for i in range(members))
    return (
        f"# {label}\n\n"
        f"Part of [[code/{repo_name}/index|{repo_name}]]. "
        f"{members} record{plural} that the graph "
        "found to be more connected to each other than to the rest of the repository.\n\n"
        "## What is in here\n\n"
        f"{bullets}\n\n"
        "---\n\n"
        "Generated from the code graph. Edit freely — your words are kept, and "
        "reindexing will not overwrite a page you have taken over.\n"
    )


def legacy_index_body(repo_name: str = "nixos") -> str:
    """The pre-#71 `render_index_page`."""
    return (
        f"# {repo_name}\n\n"
        f"Code memory for the `{repo_name}` repository.\n\n"
        "- 212 records, 340 relationships\n"
        f"- {CLUSTER_COUNT} clusters\n"
        "- 212 extracted\n\n"
        "## Clusters\n\n"
        "- [[code/nixos/cluster-0|cluster 0]] — 3 records\n"
    )


def with_frontmatter(body: str, title: str, tags: list[str]) -> str:
    return f"---\ntitle: {title}\ntags: [{', '.join(tags)}]\n---\n\n{body}"


async def seed() -> None:
    for i in range(CLUSTER_COUNT):
        body = legacy_cluster_body(f"cluster {i}", members=1 + i % 7)
        # Half carry frontmatter, the way a page read back from the vault does;
        # the match must not depend on which.
        if i % 2:
            body = with_frontmatter(body, f"cluster {i}", ["code", "cluster"])
        await sqlite_mod.upsert_page(f"{PREFIX}/cluster-{i}", f"cluster {i}", body, ["code", "cluster"])
    await sqlite_mod.upsert_page(f"{PREFIX}/index", "nixos", legacy_index_body(), ["code", "repo"])
    await sqlite_mod.upsert_page(
        WEIRD,
        "weird",
        "# weird\n\nSomeone rewrote this page by hand: the nixos flake pins "
        "home-manager to the release branch.\n",
        ["code", "cluster"],
    )
    for slug, body in HAND_AUTHORED.items():
        await sqlite_mod.upsert_page(slug, slug.rsplit("/", 1)[-1], body, ["notes"], authored_by="user")


@pytest.fixture
def settings(tmp_path):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
        code_cache_dir=tmp_path / "code-cache",
    )
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    return settings


@pytest.fixture
async def seeded(settings):
    await sqlite_mod.init_db(settings)
    await seed()
    return settings


async def _hand_authored_snapshot() -> dict[str, tuple[str, str]]:
    snapshot = {}
    for slug in HAND_AUTHORED:
        page = await sqlite_mod.get_page(slug)
        assert page is not None
        snapshot[slug] = (page["content"], page["updated_at"])
    return snapshot


def _expected_matched() -> list[str]:
    return sorted([f"{PREFIX}/cluster-{i}" for i in range(CLUSTER_COUNT)] + [f"{PREFIX}/index"])


# ── Finding ───────────────────────────────────────────────────────────────────


async def test_find_separates_the_35_stubs_from_the_page_someone_changed(seeded):
    candidates = await sqlite_mod.find_stub_pages_under(PREFIX)

    assert sorted(candidates.matched) == _expected_matched()
    assert len(candidates.matched) == 35
    assert [entry["slug"] for entry in candidates.skipped] == [WEIRD]
    assert "template" in candidates.skipped[0]["reason"]


async def test_a_stub_body_with_other_tags_is_skipped_not_matched(settings):
    await sqlite_mod.init_db(settings)
    await sqlite_mod.upsert_page(
        f"{PREFIX}/retagged", "retagged", legacy_cluster_body("retagged", 3), ["code", "cluster", "keep"]
    )
    await sqlite_mod.upsert_page(f"{PREFIX}/index", "nixos", legacy_index_body(), ["code", "cluster"])

    candidates = await sqlite_mod.find_stub_pages_under(PREFIX)

    assert candidates.matched == []
    reasons = {entry["slug"]: entry["reason"] for entry in candidates.skipped}
    assert set(reasons) == {f"{PREFIX}/retagged", f"{PREFIX}/index"}
    assert all("tags" in reason for reason in reasons.values())


async def test_a_stub_a_person_has_taken_over_is_skipped(settings):
    await sqlite_mod.init_db(settings)
    await sqlite_mod.upsert_page(
        f"{PREFIX}/mine", "mine", legacy_cluster_body("mine", 2), ["code", "cluster"], authored_by="user"
    )

    candidates = await sqlite_mod.find_stub_pages_under(PREFIX)

    assert candidates.matched == []
    assert candidates.skipped[0]["slug"] == f"{PREFIX}/mine"
    assert "user" in candidates.skipped[0]["reason"]


async def test_the_prefix_is_a_folder_not_a_like_pattern(settings):
    """`_` is a LIKE wildcard: `code/ni_os` must not reach into `code/nixos`."""
    await sqlite_mod.init_db(settings)
    await seed()

    candidates = await sqlite_mod.find_stub_pages_under("code/ni_os")

    assert candidates.matched == []
    assert candidates.skipped == []


@pytest.mark.parametrize(
    "prefix", ["projects/perceo", "daily", "code", "code/", "", "codex/nixos", "code/../projects"]
)
async def test_the_purge_refuses_anything_outside_a_code_folder(settings, prefix):
    with (
        patch.object(sqlite_mod, "list_pages_under", new=AsyncMock()) as listing,
        patch.object(sqlite_mod, "get_db") as connect,
    ):
        with pytest.raises(ValueError):
            await sqlite_mod.find_stub_pages_under(prefix)
        with pytest.raises(ValueError):
            await sqlite_mod.purge_stub_pages_under(prefix, dry_run=False)

    listing.assert_not_called()
    connect.assert_not_called()


# ── Purging ───────────────────────────────────────────────────────────────────


async def test_a_dry_run_reports_the_split_and_deletes_nothing(seeded):
    hand_before = await _hand_authored_snapshot()

    report = await sqlite_mod.purge_stub_pages_under(PREFIX, dry_run=True)

    assert report["dry_run"] is True
    assert sorted(report["matched"]) == _expected_matched()
    assert [entry["slug"] for entry in report["skipped"]] == [WEIRD]
    assert report["deleted"] == []
    assert len(await sqlite_mod.list_pages_under(PREFIX)) == 36
    assert await _hand_authored_snapshot() == hand_before


async def test_executing_deletes_exactly_the_35_stubs(seeded):
    hand_before = await _hand_authored_snapshot()
    total_before = len(await sqlite_mod.list_pages(wiki_id="default"))

    report = await sqlite_mod.purge_stub_pages_under(PREFIX, dry_run=False)

    assert sorted(report["deleted"]) == _expected_matched()
    assert len(report["deleted"]) == 35
    assert [page["slug"] for page in await sqlite_mod.list_pages_under(PREFIX)] == [WEIRD]
    assert len(await sqlite_mod.list_pages(wiki_id="default")) == total_before - 35
    assert await _hand_authored_snapshot() == hand_before


async def test_a_stub_edited_between_find_and_delete_survives(seeded):
    """The delete is pinned to the body that was checked, not just the slug."""
    real_find = sqlite_mod.find_stub_pages_under

    async def find_then_someone_edits(prefix, wiki_id="default"):
        candidates = await real_find(prefix, wiki_id)
        await sqlite_mod.upsert_page(
            f"{PREFIX}/cluster-0", "cluster 0", "# cluster 0\n\nNow it says something.\n", ["code", "cluster"]
        )
        return candidates

    with patch.object(sqlite_mod, "find_stub_pages_under", new=find_then_someone_edits):
        report = await sqlite_mod.purge_stub_pages_under(PREFIX, dry_run=False)

    assert f"{PREFIX}/cluster-0" not in report["deleted"]
    assert len(report["deleted"]) == 34
    assert await sqlite_mod.get_page(f"{PREFIX}/cluster-0") is not None
    assert any(entry["slug"] == f"{PREFIX}/cluster-0" for entry in report["skipped"])


async def test_the_stub_patterns_do_not_match_what_the_indexer_writes_now():
    """Post-#71 pages lead with narrative prose; they must never look like stubs."""
    narrative = (
        "# Geo helpers\n\nThis subsystem groups the code around `geo.py:1-2` so that "
        "callers have one place to reach for distance maths.\n"
    )
    assert not sqlite_mod.CLUSTER_STUB_RE.search(narrative)
    assert not sqlite_mod.INDEX_STUB_RE.search(narrative)
    assert sqlite_mod.CLUSTER_STUB_RE.search(legacy_cluster_body("x", 1))
    assert sqlite_mod.INDEX_STUB_RE.search(legacy_index_body("conductor-arch"))


# ── The script ────────────────────────────────────────────────────────────────


def _run_script(argv: list[str], capsys) -> tuple[int, dict]:
    from archivum.scripts import purge_stub_pages

    code = purge_stub_pages.main(argv)
    return code, json.loads(capsys.readouterr().out)


def _seed_sync(settings: Settings) -> None:
    async def go():
        await sqlite_mod.init_db(settings)
        await seed()
        for i in range(CLUSTER_COUNT):
            path = settings.wiki_dir / PREFIX / f"cluster-{i}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            page = await sqlite_mod.get_page(f"{PREFIX}/cluster-{i}")
            path.write_text(page["content"], encoding="utf-8")
        (settings.wiki_dir / PREFIX / "index.md").write_text(legacy_index_body(), encoding="utf-8")
        (settings.wiki_dir / PREFIX / "weird.md").write_text("# weird\n\nhand written\n", encoding="utf-8")

    asyncio.run(go())


def _count_under(settings: Settings, prefix: str) -> int:
    async def go():
        sqlite_mod.configure(settings)
        return len(await sqlite_mod.list_pages_under(prefix))

    return asyncio.run(go())


def test_the_script_is_a_dry_run_unless_told_otherwise(settings, capsys):
    _seed_sync(settings)

    code, report = _run_script(
        ["--db-path", str(settings.db_path), "--wiki-dir", str(settings.wiki_dir)], capsys
    )

    assert code == 0
    assert report["mode"] == "dry-run"
    assert report["prefix"] == PREFIX
    assert len(report["matched"]) == 35
    assert report["deleted"] == []
    assert _count_under(settings, PREFIX) == 36
    assert len(list((settings.wiki_dir / PREFIX).glob("*.md"))) == 36


def test_the_script_executes_removing_rows_files_and_index_entries(settings, capsys, mock_kuzu_conn):
    _seed_sync(settings)

    with patch("archivum.indexing.qdrant.delete_page", new=AsyncMock()) as qdrant_delete:
        code, report = _run_script(
            ["--db-path", str(settings.db_path), "--wiki-dir", str(settings.wiki_dir), "--execute"],
            capsys,
        )

    assert code == 0
    assert report["mode"] == "execute"
    assert report["outcome"] == "purged"
    assert len(report["deleted"]) == 35
    assert _count_under(settings, PREFIX) == 1
    assert [p.name for p in (settings.wiki_dir / PREFIX).glob("*.md")] == ["weird.md"]
    assert qdrant_delete.await_count == 35


def test_the_script_leaves_a_stub_whose_file_was_edited(settings, capsys, mock_kuzu_conn):
    """The vault file is what gets re-read on reconcile; an edited file is a person's page."""
    _seed_sync(settings)
    (settings.wiki_dir / PREFIX / "cluster-3.md").write_text("# cluster 3\n\nMy notes.\n", encoding="utf-8")

    with patch("archivum.indexing.qdrant.delete_page", new=AsyncMock()):
        code, report = _run_script(
            ["--db-path", str(settings.db_path), "--wiki-dir", str(settings.wiki_dir), "--execute"],
            capsys,
        )

    assert code == 1, "a partial purge must not exit like a complete one"
    assert f"{PREFIX}/cluster-3" not in report["deleted"]
    assert len(report["deleted"]) == 34
    assert (settings.wiki_dir / PREFIX / "cluster-3.md").exists()


def test_executing_with_nothing_to_purge_is_not_reported_as_success(settings, capsys):
    asyncio.run(sqlite_mod.init_db(settings))

    code, report = _run_script(
        ["--db-path", str(settings.db_path), "--wiki-dir", str(settings.wiki_dir), "--execute"], capsys
    )

    assert code != 0
    assert report["outcome"] == "nothing-to-purge"
    assert report["deleted"] == []


def test_the_script_refuses_a_database_that_does_not_exist(tmp_path, capsys):
    from archivum.scripts import purge_stub_pages

    missing = tmp_path / "nope.db"
    with pytest.raises(SystemExit):
        purge_stub_pages.main(["--db-path", str(missing)])
    assert not missing.exists(), "pointing at a wrong path must not create an empty vault there"
