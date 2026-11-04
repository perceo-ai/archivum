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
from pathlib import Path
from unittest.mock import AsyncMock, patch

import archivum.db.sqlite as sqlite_mod
import pytest
from archivum.code_repos import (
    MAX_INDEX_ATTEMPTS,
    _set_status,
    purge_dangling_links,
    purge_repo_scope,
    cancel_narrations,
    get_repo,
    init_repo_schema,
    narrate_repo_pages,
    resume_owed_narration,
    index_repo,
    register_repo,
    requeue_stale_indexing,
    run_pending_repo_indexing,
)

from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema

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


async def _die_mid_flight(repo) -> None:
    """Run an index that ends the way an out-of-memory kill does: no handler runs."""

    async def die(repo_arg, **_):
        raise KeyboardInterrupt  # not an `Exception`, so nothing records a failure

    with patch("archivum.code_repos._index_repo", new=die):
        with pytest.raises(KeyboardInterrupt):
            await index_repo(repo)


async def test_a_repo_that_keeps_killing_the_process_stops_being_retried(vault):  # noqa: F811
    """An ingest that outlives the process was requeued forever, from zero.

    Live, one upload ran until the backend was killed about every 61 minutes and
    the sweep put it straight back, which kept a shared SSD busy for two days.
    """
    repo = await _registered(vault)

    for _ in range(MAX_INDEX_ATTEMPTS - 1):
        await _die_mid_flight(repo)
        assert await requeue_stale_indexing(older_than_seconds=0) == 1

    await _die_mid_flight(repo)
    assert await requeue_stale_indexing(older_than_seconds=0) == 0

    stored = await get_repo(repo.scope, wiki_id="default")
    assert stored is not None
    assert stored.status == "error"
    assert f"{MAX_INDEX_ATTEMPTS} attempts" in (stored.error or "")
    assert await run_pending_repo_indexing(narrate=False) == 0


async def test_asking_again_gives_a_failed_repo_a_fresh_set_of_attempts(vault):  # noqa: F811
    repo = await _registered(vault)
    for _ in range(MAX_INDEX_ATTEMPTS):
        await _die_mid_flight(repo)
        await requeue_stale_indexing(older_than_seconds=0)

    repo = await register_repo(path=Path(repo.path), wiki_id="default", name=repo.name)
    assert repo.status == "pending"

    await _die_mid_flight(repo)
    assert await requeue_stale_indexing(older_than_seconds=0) == 1


async def test_a_finished_index_clears_its_attempts(vault):  # noqa: F811
    """Restarts spread over months must not add up to a limit on a healthy repo."""
    repo = await _registered(vault)
    await _die_mid_flight(repo)
    await requeue_stale_indexing(older_than_seconds=0)

    await index_repo(repo, write_pages=False)

    for _ in range(MAX_INDEX_ATTEMPTS - 1):
        await _die_mid_flight(repo)
        assert await requeue_stale_indexing(older_than_seconds=0) == 1


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


async def test_forget_does_not_let_narration_delete_the_pages(vault):  # noqa: F811
    """`forget` drops the registration and keeps the pages on purpose.

    A missing register row alone does not say which kind of gone this is, and
    treating it as a purge would have erased pages a person edited by hand.
    The knowledge objects are the difference: `forget` leaves them.
    """
    repo = await _registered(vault)
    page_dir = vault.wiki_dir / "code" / "atlas"
    page_dir.mkdir(parents=True, exist_ok=True)
    (page_dir / "hand-written.md").write_text("# mine\n", encoding="utf-8")

    async def writes(repo_arg, **_):
        # Unregistered mid-narration, as `forget` does — records left behind.
        async with sqlite_mod.get_db() as conn:
            await conn.execute("DELETE FROM code_repos WHERE scope=?", (repo_arg.scope,))
            await conn.execute(
                "INSERT OR IGNORE INTO knowledge_objects "
                "(id, kind, label, scope, confidence, extraction_method, properties) "
                "VALUES (?,?,?,?,?,?,?)",
                (f"{repo_arg.scope}:sym", "symbol", "sym", repo_arg.scope, 1.0, "EXTRACTED", "{}"),
            )
            await conn.commit()
        return 2

    with patch("archivum.code_repos.write_repo_pages", new=writes):
        await narrate_repo_pages(repo, settings=vault)

    assert (page_dir / "hand-written.md").exists(), "forget must keep the pages"


_CITATION = Citation(source_id="s", chunk_id="c", span_start=None, span_end=None, quote=None)


async def _seed_link(src: str, dst: str, *, scope: str = "cross_repo") -> str:
    edge_id = f"{src}__same_symbol_as__{dst}"
    async with sqlite_mod.get_db() as conn:
        await init_knowledge_schema(conn)
        await KnowledgeRepository(conn).upsert_relationship(
            KnowledgeRelationship(
                id=edge_id,
                src_id=src,
                dst_id=dst,
                rel_type="same_symbol_as",
                scope=scope,
                confidence=0.5,
                extraction_method="AMBIGUOUS",
                citations=[_CITATION],
                properties={},
            )
        )
    return edge_id


async def _seed_object(object_id: str, scope: str) -> None:
    async with sqlite_mod.get_db() as conn:
        await init_knowledge_schema(conn)
        await KnowledgeRepository(conn).upsert_object(
            KnowledgeObject(
                id=object_id,
                kind="symbol",
                label=object_id,
                scope=scope,
                confidence=1.0,
                extraction_method="EXTRACTED",
                citations=[_CITATION],
                properties={},
            )
        )


async def _surviving_edges() -> tuple[set[str], int]:
    async with sqlite_mod.get_db() as conn:
        async with conn.execute("SELECT id FROM knowledge_relationships") as cursor:
            edges = {row[0] for row in await cursor.fetchall()}
        async with conn.execute(
            "SELECT COUNT(*) FROM knowledge_citations WHERE knowledge_type='relationship'"
        ) as cursor:
            citations = (await cursor.fetchone())[0]
    return edges, citations


async def test_purging_a_repo_takes_the_links_that_reached_it(vault):  # noqa: F811
    """`cross_repo` edges have their own scope, so a scope-matched delete missed them."""
    repo = await _registered(vault)
    await _seed_object("gone", repo.scope)
    await _seed_object("kept", "repo:default:other")
    await _seed_object("kept-too", "repo:default:third")
    await _seed_link("gone", "kept")
    await _seed_link("kept", "gone")
    unrelated = await _seed_link("kept", "kept-too")
    # Recorded memory: no index rebuilds it, so a purge must not take it.
    recorded = await _seed_link("fix", "gone", scope="bridge")

    await purge_repo_scope(repo.scope, wiki_id="default")

    assert await _surviving_edges() == ({unrelated, recorded}, 2)


async def test_dangling_links_are_purged_and_nothing_else(vault):  # noqa: F811
    await sqlite_mod.init_db(vault)
    await _seed_object("a", "repo:default:a")
    await _seed_object("b", "repo:default:b")
    live = await _seed_link("a", "b")
    await _seed_link("a", "missing")
    await _seed_link("missing", "b")
    # An incremental index removes symbols before rewriting them, and nothing
    # rebuilds a recorded link, so these must outlive a sweep.
    recorded = await _seed_link("fix", "missing", scope="bridge")
    other = await _seed_link("missing", "also-missing", scope="repo:default:a")

    assert await purge_dangling_links(batch_size=1) == 2

    assert await _surviving_edges() == ({live, recorded, other}, 3)


async def test_two_first_callers_can_both_initialise_the_schema(vault):  # noqa: F811
    """Both read the old columns before either alters the table.

    The loser used to fail its whole request on a duplicate column; the column
    existing is what both of them wanted.
    """
    await sqlite_mod.init_db(vault)

    async def init_once():
        async with sqlite_mod.get_db() as conn:
            await init_repo_schema(conn)

    await asyncio.gather(*(init_once() for _ in range(6)))

    async with sqlite_mod.get_db() as conn:
        cursor = await conn.execute("PRAGMA table_info(code_repos)")
        assert "narration_owed" in {row[1] for row in await cursor.fetchall()}
