"""A repository is named for what it is, not for where it happens to sit.

`register_repo` used to fall back to the basename of the checkout directory when
no name was passed. A repository cloned into a directory called `nixos` was
remembered as `nixos`, and every repository checked out under a same-named
directory on that machine collided into one namespace. The origin remote is the
repository's identity; the directory name is only a last resort.
"""

# ruff: noqa: F811 - `vault` is an imported fixture, requested by parameter name.

from __future__ import annotations

import subprocess
from pathlib import Path

import archivum.db.sqlite as sqlite_mod
import pytest
from archivum import code_repos
from archivum.code_pages import repo_folder
from archivum.code_repos import register_repo

# Shared with test_code_pages: its repo/indexing helpers, plus the `vault`
# fixture and autouse git check. Pytest registers a fixture under the name it is
# imported as, so the fixtures must keep their names.
from test_code_pages import _needs_git, _reindex, fake_narrator, make_repo, vault  # noqa: F401

CONDUCTOR_REMOTE = "https://github.com/perceo-ai/conductor-arch.git"


def add_origin(repo: Path, url: str) -> Path:
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)
    return repo


async def _code_slugs(wiki_id: str = "default") -> set[str]:
    return {
        row["slug"]
        for row in await sqlite_mod.list_pages(wiki_id)
        if row["slug"].startswith("code/")
    }


async def _code_folders(wiki_id: str = "default") -> set[str]:
    return {"/".join(slug.split("/")[:2]) for slug in await _code_slugs(wiki_id)}


# ── Parsing the remote ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/perceo-ai/conductor-arch.git",
        "https://github.com/perceo-ai/conductor-arch",
        "git@github.com:perceo-ai/conductor-arch.git",
        "ssh://git@gitlab.example.com:2222/perceo-ai/conductor-arch.git",
        "https://github.com/Perceo-AI/Conductor-Arch.git/",
    ],
)
def test_https_and_ssh_remotes_name_the_same_repository(url):
    assert code_repos._identity_from_remote_url(url) == "perceo-ai-conductor-arch"


def test_characters_a_path_segment_cannot_hold_are_slugged_not_fatal():
    assert code_repos._identity_from_remote_url("https://host/team space/my repo!.git") == "team-space-my-repo"


@pytest.mark.parametrize("url", ["", "   ", "https://github.com/", "git@github.com:solo.git"])
def test_a_remote_without_owner_and_repo_gives_no_identity(url):
    assert code_repos._identity_from_remote_url(url) is None


# ── Registering ───────────────────────────────────────────────────────────────


async def test_a_misleading_checkout_directory_does_not_name_the_repo(vault, tmp_path):
    await sqlite_mod.init_db(vault)
    checkout = add_origin(make_repo(tmp_path, name="nixos"), CONDUCTOR_REMOTE)

    repo = await register_repo(path=checkout, wiki_id="default")

    assert repo.name != "nixos"
    assert "conductor-arch" in repo.name
    assert repo_folder(repo.name) != "code/nixos"
    assert "conductor-arch" in repo_folder(repo.name)


async def test_two_repos_in_same_named_directories_get_two_namespaces(vault, tmp_path):
    await sqlite_mod.init_db(vault)
    widgets = add_origin(make_repo(tmp_path / "a", name="work"), "https://github.com/acme/widgets.git")
    sprockets = add_origin(make_repo(tmp_path / "b", name="work"), "git@github.com:acme/sprockets.git")

    first = await register_repo(path=widgets, wiki_id="default")
    second = await register_repo(path=sprockets, wiki_id="default")

    assert first.name != second.name
    assert repo_folder(first.name) != repo_folder(second.name)
    assert "work" not in {first.name, second.name}
    assert "code/work" not in {repo_folder(first.name), repo_folder(second.name)}
    assert first.scope != second.scope


async def test_a_repo_without_an_origin_falls_back_to_its_directory_name(vault, tmp_path):
    await sqlite_mod.init_db(vault)
    checkout = make_repo(tmp_path, name="atlas")  # a git repo, but no origin

    repo = await register_repo(path=checkout, wiki_id="default")

    assert repo.name == "atlas"


async def test_a_directory_that_is_not_a_git_repo_falls_back_to_its_name(vault, tmp_path):
    await sqlite_mod.init_db(vault)
    plain = tmp_path / "loose-files"
    plain.mkdir()
    (plain / "notes.py").write_text("x = 1\n", encoding="utf-8")

    repo = await register_repo(path=plain, wiki_id="default")

    assert repo.name == "loose-files"


async def test_a_subdirectory_of_a_repo_does_not_borrow_the_whole_repos_identity(vault, tmp_path):
    """Indexing two subdirectories of one monorepo must not collide into one name."""
    await sqlite_mod.init_db(vault)
    monorepo = add_origin(
        make_repo(tmp_path, name="mono", extra={"backend/app.py": "x = 1\n"}),
        "https://github.com/acme/mono.git",
    )

    repo = await register_repo(path=monorepo / "backend", wiki_id="default")

    assert repo.name == "backend"


async def test_an_explicit_name_still_wins_over_the_remote(vault, tmp_path):
    await sqlite_mod.init_db(vault)
    checkout = add_origin(make_repo(tmp_path, name="nixos"), CONDUCTOR_REMOTE)

    repo = await register_repo(path=checkout, wiki_id="default", name="chosen")

    assert repo.name == "chosen"


# ── Indexing ──────────────────────────────────────────────────────────────────


async def test_reindexing_the_same_repo_updates_its_namespace_in_place(vault, tmp_path, mock_kuzu_conn):
    await sqlite_mod.init_db(vault)
    checkout = add_origin(make_repo(tmp_path, name="nixos"), CONDUCTOR_REMOTE)

    repo = await register_repo(path=checkout, wiki_id="default")
    await _reindex(vault)
    folder = repo_folder(repo.name)
    assert "conductor-arch" in folder
    first_slugs = await _code_slugs()
    first_count = len(await sqlite_mod.list_pages_under(folder))
    assert first_count > 0

    again = await register_repo(path=checkout, wiki_id="default")
    await _reindex(vault)
    second_slugs = await _code_slugs()

    assert again.name == repo.name
    assert len(await sqlite_mod.list_pages_under(folder)) == first_count
    assert second_slugs == first_slugs, "a second run must not open a parallel code/ folder"
    assert await _code_folders() == {folder}


async def test_reindexing_under_the_corrected_namespace_writes_real_content(vault, tmp_path, mock_kuzu_conn):
    """End to end: the `nixos` checkout of conductor-arch lands under its own name, as prose."""
    await sqlite_mod.init_db(vault)
    checkout = add_origin(make_repo(tmp_path, name="nixos"), CONDUCTOR_REMOTE)

    repo = await register_repo(path=checkout, wiki_id="default")
    await _reindex(vault, narrator=fake_narrator)

    folder = repo_folder(repo.name)
    assert "conductor-arch" in folder
    pages = await sqlite_mod.list_pages_under(folder)
    assert pages, "indexing should have written pages under the derived namespace"
    assert await sqlite_mod.list_pages_under("code/nixos") == []

    bodies = [page["content"] for page in pages]
    real = [
        body for body in bodies
        if not sqlite_mod.CLUSTER_STUB_RE.search(body)
        and not sqlite_mod.INDEX_STUB_RE.search(body)
    ]
    assert real, "freshly indexed pages must not be legacy metadata stubs"
    assert any("This subsystem groups the code around" in body for body in real), (
        "at least one page should carry the narrator's prose"
    )

    slugs_before = sorted(page["slug"] for page in pages)
    await register_repo(path=checkout, wiki_id="default")
    await _reindex(vault, narrator=fake_narrator)

    slugs_after = sorted(page["slug"] for page in await sqlite_mod.list_pages_under(folder))
    assert slugs_after == slugs_before
    assert await sqlite_mod.list_pages_under("code/nixos") == []
    assert await _code_folders() == {folder}
