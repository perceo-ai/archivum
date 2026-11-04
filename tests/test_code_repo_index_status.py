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

import asyncio
from unittest.mock import AsyncMock, patch

import archivum.db.sqlite as sqlite_mod
import pytest
from archivum.code_repos import (
    _set_status,
    cancel_narrations,
    get_repo,
    narrate_repo_pages,
    resume_owed_narration,
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


async def test_a_repo_is_ready_before_its_pages_are_narrated(vault):  # noqa: F811
    """Readiness means retrieval works, and pages are not part of that.

    Narration is one model call per cluster — up to 150 at concurrency 4 with a
    180s timeout, so close to two hours. Gating `ready` on it was a livelock: a
    restart during narration left the row claimed, the stale sweep requeued it,
    and the next run began the same two hours again. Live, a repository whose
    graph was built in minutes never once reached `ready`.
    """
    repo = await _registered(vault)
    status_while_writing: list[str] = []

    async def slow_pages(repo_arg, **_):
        stored = await get_repo(repo_arg.scope, wiki_id="default")
        status_while_writing.append(stored.status if stored else "missing")
        return 4

    with patch("archivum.code_repos.write_repo_pages", new=slow_pages):
        await index_repo(repo)

    assert status_while_writing == ["ready"], "pages must not gate readiness"
    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None
    assert stored.status == "ready"
    assert stored.pages == 4
    assert stored.nodes > 0, "the graph is what readiness actually depends on"


async def test_failing_to_write_pages_leaves_the_index_usable(vault):  # noqa: F811
    """A page that cannot be narrated costs its page, not the whole index."""
    repo = await _registered(vault)

    async def pages_explode(repo_arg, **_):
        raise RuntimeError("the model could not be reached")

    with patch("archivum.code_repos.write_repo_pages", new=pages_explode):
        indexed = await index_repo(repo)

    assert indexed.status == "ready"
    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None and stored.status == "ready"
    assert stored.nodes > 0


async def test_the_worker_does_not_hold_its_queue_for_narration(vault):  # noqa: F811
    """Narration must not decide when the next repository gets indexed.

    Page writing is one model call per cluster and can run for close to two
    hours. Doing it on the queue meant marking the first repository `ready`
    released nothing: a repository uploaded during narration waited for it.
    """
    repo = await _registered(vault)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_narration(repo_arg, **_):
        started.set()
        await release.wait()
        return 1

    with patch("archivum.code_repos.write_repo_pages", new=slow_narration):
        # `narrate=False` is what the worker passes.
        indexed = await asyncio.wait_for(
            run_pending_repo_indexing(settings=vault, narrate=False), timeout=5
        )
        assert indexed == 1
        # The sweep returned while narration is still going.
        await asyncio.wait_for(started.wait(), timeout=5)
        stored = await get_repo(repo.scope, wiki_id="default")
        assert stored is not None and stored.status == "ready"
        release.set()
        await cancel_narrations()


async def test_narration_is_stopped_with_the_worker(vault):  # noqa: F811
    """A detached task that outlives shutdown is a leak, so it is cancelled."""
    await _registered(vault)
    started = asyncio.Event()

    async def never_finishes(repo_arg, **_):
        started.set()
        await asyncio.Event().wait()

    with patch("archivum.code_repos.write_repo_pages", new=never_finishes):
        await run_pending_repo_indexing(settings=vault, narrate=False)
        await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.wait_for(cancel_narrations(), timeout=5)

    from archivum.code_repos import _narrations

    assert _narrations == {}


async def test_a_reindex_cancels_the_narration_it_supersedes(vault):  # noqa: F811
    """The older narration describes a graph that has just been replaced.

    Letting both finish meant the older one could write its pages over the
    newer one's, or report `ready` for an index that had since failed.
    """
    repo = await _registered(vault)
    first_started = asyncio.Event()

    async def hangs(repo_arg, **_):
        first_started.set()
        await asyncio.Event().wait()

    with patch("archivum.code_repos.write_repo_pages", new=hangs):
        await run_pending_repo_indexing(settings=vault, narrate=False)
        await asyncio.wait_for(first_started.wait(), timeout=5)
        from archivum.code_repos import _narrations, _spawn_narration

        first = _narrations[repo.scope]
        _spawn_narration(repo, vault)  # as a reindex would
        assert first.cancelled() or first.done() or True
        await asyncio.sleep(0)
        assert first.cancelled(), "the superseded narration must be cancelled"
        assert _narrations[repo.scope] is not first
        await cancel_narrations()


async def test_a_stale_page_count_is_discarded(vault):  # noqa: F811
    """A page count only lands if the row still holds the index it came from."""
    repo = await _registered(vault)

    async def pages_then_reindex(repo_arg, **_):
        # Stand in for a reindex finishing while narration ran: the row moves
        # to a new index, so this narration's count no longer describes it.
        await _set_status(repo_arg.scope, "ready", indexed_at="2099-01-01T00:00:00+00:00")
        return 7

    with patch("archivum.code_repos.write_repo_pages", new=pages_then_reindex):
        await narrate_repo_pages(repo, settings=vault)

    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None
    assert stored.pages == 0, "a count from a replaced index must not be written"


async def test_shutdown_during_a_handover_does_not_start_new_narration(vault):  # noqa: F811
    """Cancelling the replacement must not be read as the predecessor dying.

    The handover catches the predecessor's cancellation; catching this task's
    own as well meant shutdown began a fresh narration and then waited out the
    whole run — the restart stall this work exists to remove.
    """
    repo = await _registered(vault)
    runs = 0
    first_started = asyncio.Event()

    async def hangs(repo_arg, **_):
        nonlocal runs
        runs += 1
        first_started.set()
        await asyncio.Event().wait()

    with patch("archivum.code_repos.write_repo_pages", new=hangs):
        from archivum.code_repos import _spawn_narration

        _spawn_narration(repo, vault)
        await asyncio.wait_for(first_started.wait(), timeout=5)
        assert runs == 1

        # A reindex hands over, then shutdown lands mid-handover.
        _spawn_narration(repo, vault)
        await asyncio.wait_for(cancel_narrations(), timeout=5)

    assert runs == 1, "shutdown must not start a narration it then waits for"
    from archivum.code_repos import _narrations

    assert _narrations == {}


async def test_owed_narration_is_resumed_after_a_restart(vault):  # noqa: F811
    """A restart cancels the task; nothing else would ever look again.

    The repository is `ready` and the queue selects `pending` only, so the
    pages were simply never written. The flag is what survives the restart.
    """
    repo = await _registered(vault)
    first_started = asyncio.Event()

    async def hangs(repo_arg, **_):
        first_started.set()
        await asyncio.Event().wait()

    with patch("archivum.code_repos.write_repo_pages", new=hangs):
        await run_pending_repo_indexing(settings=vault, narrate=False)
        await asyncio.wait_for(first_started.wait(), timeout=5)
        stored = await get_repo(repo.scope, wiki_id="default")
        assert stored is not None and stored.narration_owed is True
        # The restart.
        await cancel_narrations()

    # Still owed, because the pages never landed.
    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None and stored.narration_owed is True

    resumed_started = asyncio.Event()

    async def writes(repo_arg, **_):
        resumed_started.set()
        return 3

    with patch("archivum.code_repos.write_repo_pages", new=writes):
        assert await resume_owed_narration(settings=vault) == 1
        await asyncio.wait_for(resumed_started.wait(), timeout=5)
        await asyncio.sleep(0.1)

    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None
    assert stored.pages == 3
    assert stored.narration_owed is False, "a written page is no longer owed"


async def test_a_purge_stops_the_narration_that_would_rewrite_its_pages(vault):  # noqa: F811
    """A narration in flight goes on to write the markdown being deleted.

    Markdown is the source of truth, so leaving those files behind means the
    vault watcher imports the purged repository straight back.
    """
    repo = await _registered(vault)
    started = asyncio.Event()

    async def hangs(repo_arg, **_):
        started.set()
        await asyncio.Event().wait()

    with patch("archivum.code_repos.write_repo_pages", new=hangs):
        await run_pending_repo_indexing(settings=vault, narrate=False)
        await asyncio.wait_for(started.wait(), timeout=5)

        from archivum.code_repos import _narrations, purge_repo_scope

        assert repo.scope in _narrations
        await asyncio.wait_for(
            purge_repo_scope(repo.scope, wiki_id="default"), timeout=10
        )
        assert repo.scope not in _narrations, "the writer must be gone first"

    assert await get_repo(repo.scope, wiki_id="default") is None
