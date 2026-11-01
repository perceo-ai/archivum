"""A repository index run always leaves the row in a state the queue can act on.

A live vault was found with eleven repositories stuck at `indexing`, zero nodes
and a null `indexed_at`, permanently. Two gaps produced that. `index_repo` set a
status only on its success path, and the upload route catches `RepoError` only —
so the `sqlite3.OperationalError` that ingest actually raised escaped as a 500
with the row still claimed. And nothing ever selected `indexing` again: the
queue takes `pending`, so a row claimed by a process that then died of an
out-of-memory kill was never looked at again.
"""

# ruff: noqa: F811 - `vault` is an imported fixture, requested by parameter name.

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import archivum.db.sqlite as sqlite_mod
import pytest
from archivum.code_repos import (
    get_repo,
    index_repo,
    register_repo,
    requeue_stale_indexing,
    run_pending_repo_indexing,
)

from test_code_pages import _needs_git, make_repo, vault  # noqa: F401


@pytest.fixture(autouse=True)
def _git(_needs_git):  # noqa: F811
    return None


@pytest.fixture(autouse=True)
def _settings(vault):  # noqa: F811
    with patch("archivum.config.get_settings", return_value=vault), patch(
        "archivum.code_repos.get_settings", return_value=vault
    ):
        yield vault


async def _registered(vault, name="atlas"):  # noqa: F811
    await sqlite_mod.init_db(vault)
    repo = make_repo(vault.code_cache_dir / "src", name=name)
    return await register_repo(path=repo, wiki_id="default", name=name)


async def test_a_failed_index_leaves_the_row_in_error_not_indexing(vault):  # noqa: F811
    repo = await _registered(vault)

    boom = OSError("database is locked")
    with patch("archivum.code_repos._index_repo", new=AsyncMock(side_effect=boom)):
        with pytest.raises(OSError):
            await index_repo(repo)

    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None
    # `error` is the state an operator and the UI can both act on. `indexing`
    # is a lie that no sweep will ever revisit.
    assert stored.status == "error"
    assert "database is locked" in (stored.error or "")


async def test_the_row_is_claimed_before_the_work_starts(vault):  # noqa: F811
    repo = await _registered(vault)
    seen: list[str] = []

    async def record_then_fail(repo_arg, **_):
        stored = await get_repo(repo_arg.scope, wiki_id="default")
        seen.append(stored.status if stored else "missing")
        raise OSError("stop here")

    with patch("archivum.code_repos._index_repo", new=record_then_fail):
        with pytest.raises(OSError):
            await index_repo(repo)

    # Claimed up front, so the background queue cannot start a second ingest of
    # the same repository alongside an inline one from the upload route.
    assert seen == ["indexing"]


async def test_abandoned_indexing_rows_are_returned_to_the_queue(vault):  # noqa: F811
    repo = await _registered(vault)

    async def die_mid_flight(repo_arg, **_):
        raise KeyboardInterrupt  # stands in for the process going away

    with patch("archivum.code_repos._index_repo", new=die_mid_flight):
        with pytest.raises(KeyboardInterrupt):
            await index_repo(repo)

    # Nothing marked it, so it reads `indexing` with no one working on it.
    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None and stored.status == "indexing"

    # A fresh row is not stolen from a worker that is genuinely mid-ingest.
    assert await requeue_stale_indexing(older_than_seconds=3600) == 0
    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None and stored.status == "indexing"

    # Once it is older than the cutoff it goes back on the queue.
    assert await requeue_stale_indexing(older_than_seconds=0) == 1
    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None and stored.status == "pending"


async def test_the_queue_records_a_failure_without_stopping(vault):  # noqa: F811
    first = await _registered(vault, name="atlas")
    second = await _registered(vault, name="borealis")

    async def fail_atlas(repo_arg, **_):
        if repo_arg.name == "atlas":
            raise OSError("database is locked")
        return repo_arg

    with patch("archivum.code_repos._index_repo", new=fail_atlas):
        indexed = await run_pending_repo_indexing(settings=vault)

    assert indexed == 1  # borealis still got its turn
    stored_first = await get_repo(first.scope, wiki_id="default")
    assert stored_first is not None and stored_first.status == "error"
    assert "database is locked" in (stored_first.error or "")
    # borealis is left as the stub left it — the real `_index_repo` is what
    # writes `ready`, and this test is about the failure not stopping the sweep.
    assert await get_repo(second.scope, wiki_id="default") is not None
