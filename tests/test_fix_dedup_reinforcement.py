"""The second time a known error is fixed, memory gets stronger, not longer.

A fix used to be keyed by the session that produced it, so every recurrence of
the same trouble wrote a fresh `fix:<source-id>` page beside the old one. Recall
then answered "have I hit this before?" with several near-identical pages, none
of which knew the trouble had come back. A recurrence has to land on the record
that already exists: one page, more citations, more confidence.

These drive `record_session_work` end to end against a real repository, because
the defect lived in how the pieces were wired, not in any one of them.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiosqlite
import pytest

from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.fixes import Fix, recall_fixes, remember_fix
from archivum.knowledge.models import Citation, KnowledgeObject
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema
from archivum.sessions import record_session_work

WIKI = "default"
SCOPE = f"wiki:{WIKI}"

# The same trouble, reported twice: timestamps, pids and temp paths all differ,
# and the second report drops the errno and rewords the prose around it.
FIRST = (
    "2026-10-23 14:02:11 pid=4821 FileNotFoundError: [Errno 2] No such file or "
    "directory: '/tmp/run-9f21/out.json' when the exporter finishes"
)
SECOND = (
    "Export crashed again at 2026-10-24 09:17:45 (pid=13377): FileNotFoundError: "
    "No such file or directory: '/tmp/run-a07c/out.json'"
)
THIRD = "FileNotFoundError: [Errno 2] No such file or directory: '/home/ci/build-55/out.json'"


def _conversation(request: str, *, diagnosis: str, path: str, ends_passing: bool = True) -> Conversation:
    calls = (
        ToolCall(name="Bash", arguments={"command": "pytest tests/test_export.py"}, result="1 failed", ok=False),
        ToolCall(name="Edit", arguments={"file_path": path}, result="ok", ok=True),
        ToolCall(
            name="Bash",
            arguments={"command": "pytest tests/test_export.py"},
            result="1 passed" if ends_passing else "1 failed",
            ok=ends_passing,
        ),
    )
    return Conversation(
        session_id="s",
        interface="claude_code_native",
        started_at="2026-10-23T14:02:11Z",
        turns=(
            Turn(role="user", text=request, ts="2026-10-23T14:02:11Z"),
            Turn(role="assistant", text=diagnosis, ts="2026-10-23T14:03:00Z", tool_calls=calls),
        ),
        scope="personal",
        origin_uri="",
    )


FIRST_SESSION = _conversation(
    FIRST,
    diagnosis="The exporter wrote into its run directory before creating it.",
    path="/work/app/export.py",
)
SECOND_SESSION = _conversation(
    SECOND,
    diagnosis=(
        "Same cause as before: the run directory is created lazily, and the "
        "retry path skipped mkdir entirely, so out.json had nowhere to go."
    ),
    path="/work/app/retry.py",
)
UNRESOLVED_SESSION = _conversation(
    "2026-10-25 08:00:00 pid=9 FileNotFoundError: [Errno 2] No such file or directory: '/tmp/run-0000/out.json'",
    diagnosis="Trying a different mkdir call.",
    path="/work/app/export.py",
    ends_passing=False,
)


@pytest.fixture
async def repo():
    conn = await aiosqlite.connect(":memory:")
    await init_knowledge_schema(conn)
    # No registered code repositories and no vector store: this is about the
    # canonical record, and both of those are best-effort around it.
    with (
        patch("archivum.sessions.list_repos", new=AsyncMock(return_value=[])),
        patch("archivum.db.qdrant_client.upsert_fix", new=AsyncMock()),
        patch("archivum.db.qdrant_client.search_fixes", new=AsyncMock(return_value=[])),
    ):
        yield KnowledgeRepository(conn)
    await conn.close()


async def _record(repo: KnowledgeRepository, conversation: Conversation, source_id: str) -> None:
    await record_session_work(repo, conversation=conversation, source_id=source_id, wiki_id=WIKI)


async def _fixes(repo: KnowledgeRepository):
    return await repo.list_objects(kind="fix", scope=SCOPE, limit=100)


async def test_a_recurring_error_reinforces_one_atom_and_recall_finds_it(repo):
    await _record(repo, FIRST_SESSION, "src-first")
    [after_first] = await _fixes(repo)

    await _record(repo, SECOND_SESSION, "src-second")
    objects = await _fixes(repo)

    assert len(objects) == 1, [obj.id for obj in objects]
    [fix] = objects
    assert fix.id == after_first.id
    assert fix.properties["occurrences"] == 2
    assert sorted({c.source_id for c in fix.citations}) == ["src-first", "src-second"]
    assert len(fix.citations) == 2
    assert fix.confidence > after_first.confidence
    assert fix.properties["changed_paths"] == ["/work/app/export.py", "/work/app/retry.py"]
    # Both sessions' causes were real; the fuller statement is the one kept.
    assert fix.properties["diagnosis"].startswith("Same cause as before")

    found = await recall_fixes(repo, symptom=THIRD, wiki_id=WIKI)
    print(
        f"\nrecall({THIRD!r}) -> {[f.id for f in found]} "
        f"occurrences={found[0].properties['occurrences'] if found else None} "
        f"confidence={found[0].confidence if found else None}"
    )
    assert [f.id for f in found] == [fix.id]


async def test_the_same_error_twice_is_one_page_not_two(repo):
    await _record(repo, FIRST_SESSION, "src-first")
    await _record(repo, SECOND_SESSION, "src-second")

    objects = await _fixes(repo)
    assert len(objects) == 1


async def test_recapturing_the_same_session_is_not_a_recurrence(repo):
    """A transcript captured twice is one occurrence; only a new session counts."""
    await _record(repo, FIRST_SESSION, "src-first")
    [before] = await _fixes(repo)
    await _record(repo, FIRST_SESSION, "src-first")
    [after] = await _fixes(repo)

    assert after.properties["occurrences"] == 1
    assert after.confidence == before.confidence
    assert len(after.citations) == 1


async def test_an_unresolved_recurrence_changes_nothing(repo):
    await _record(repo, FIRST_SESSION, "src-first")
    await _record(repo, SECOND_SESSION, "src-second")
    [before] = await _fixes(repo)

    await _record(repo, UNRESOLVED_SESSION, "src-unresolved")

    objects = await _fixes(repo)
    assert len(objects) == 1
    [after] = objects
    assert after == before
    assert after.properties == before.properties
    assert after.confidence == before.confidence
    assert after.citations == before.citations
    # The session itself is still recorded; it just fixed nothing.
    assert await repo.get_object("session:src-unresolved") is not None


async def test_a_verified_fix_is_never_downgraded_by_an_unverified_recurrence(repo):
    await _record(repo, FIRST_SESSION, "src-first")
    unverified = Conversation(
        session_id="s",
        interface="claude_code_native",
        started_at="",
        turns=(
            Turn(role="user", text=SECOND, ts=""),
            Turn(
                role="assistant",
                text="Created the run dir.",
                ts="",
                tool_calls=(ToolCall(name="Edit", arguments={"file_path": "/work/app/export.py"}, ok=True),),
            ),
        ),
        scope="personal",
        origin_uri="",
    )
    await _record(repo, unverified, "src-unverified")

    [fix] = await _fixes(repo)
    assert fix.properties["verified_by"] == "pytest tests/test_export.py"
    assert fix.properties["occurrences"] == 2


async def test_the_atom_is_real_text_with_real_edges(repo):
    """The edges accumulate evidence the way the object does. Reusing one fix id
    across sessions means reusing its edges too, and an edge that kept only
    the latest citation forgot every earlier session that reached the code."""
    symbol = KnowledgeObject(
        id="symbol:app:export.write_results",
        kind="symbol",
        label="write_results",
        scope="code:app",
        confidence=1.0,
        extraction_method="EXTRACTED",
        citations=[Citation(source_id="code", chunk_id="/work/app/export.py", span_start=None, span_end=None, quote="def write_results")],
        properties={},
    )
    await repo.upsert_object(symbol)
    with patch("archivum.sessions._symbols_touched", new=AsyncMock(return_value=[symbol])):
        await _record(repo, FIRST_SESSION, "src-first")
        await _record(repo, SECOND_SESSION, "src-second")
    [fix] = await _fixes(repo)

    assert "FileNotFoundError" in fix.properties["symptom"]
    assert "run directory" in fix.properties["diagnosis"]

    edges = await repo.list_relationships(node_id=fix.id)
    by_type = {rel.rel_type: rel for rel in edges}
    assert {"remembers", "fixes"} <= set(by_type), edges
    for rel_type in ("remembers", "fixes"):
        sources = sorted(c.source_id for c in by_type[rel_type].citations)
        assert sources == ["src-first", "src-second"], (rel_type, sources)
    assert by_type["fixes"].dst_id == symbol.id


async def test_opposite_errors_with_the_same_words_stay_two_atoms(repo):
    """Same words, reversed meaning: which side never acknowledged whom is the
    whole diagnosis. A word-set score calls these identical (1.0), and merging
    them would answer either error with the other's cause at raised confidence."""
    worker_side = _conversation(
        "TimeoutError: the worker never acknowledged the scheduler heartbeat",
        diagnosis="The worker's ack loop was blocked on a full queue.",
        path="/work/app/worker.py",
    )
    scheduler_side = _conversation(
        "TimeoutError: the scheduler never acknowledged the worker heartbeat",
        diagnosis="The scheduler dropped heartbeats while rebalancing.",
        path="/work/app/scheduler.py",
    )
    await _record(repo, worker_side, "src-worker")
    await _record(repo, scheduler_side, "src-scheduler")

    objects = await _fixes(repo)
    assert len(objects) == 2, [obj.properties["symptom"] for obj in objects]
    diagnoses = sorted(obj.properties["diagnosis"] for obj in objects)
    assert diagnoses == [
        "The scheduler dropped heartbeats while rebalancing.",
        "The worker's ack loop was blocked on a full queue.",
    ]
    assert all(obj.properties["occurrences"] == 1 for obj in objects)
    assert all(obj.confidence == 0.9 for obj in objects)


async def test_concurrent_recurrences_lose_no_evidence(tmp_path):
    """transcript_watch and the MCP server each open their own connection, so
    two sessions reporting the same trouble can write at once. Each must see
    the other's write, not the same prior record, and none may fail on the
    lock: capture is a path that must not raise."""
    import asyncio

    import archivum.db.sqlite as sqlite_mod
    import archivum.fixes as fixes_mod
    from archivum.config import Settings

    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
        code_cache_dir=tmp_path / "code-cache",
    )
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    await sqlite_mod.init_db(settings)

    # Widen the read-to-write window so every caller reads before any writes,
    # which is the interleaving that loses evidence when nothing serialises it.
    real_lookup = fixes_mod._recurrence_of

    async def slow_lookup(*args, **kwargs):
        found = await real_lookup(*args, **kwargs)
        await asyncio.sleep(0.2)
        return found

    fix = Fix(
        symptom="FileNotFoundError: No such file or directory: '/tmp/run/out",
        diagnosis="The run directory was never created.",
        changed_paths=["/work/app/export.py"],
        verified_by="pytest",
    )
    sources = ["src-a", "src-b", "src-c"]

    async def one(source_id: str) -> None:
        async with sqlite_mod.get_db() as conn:
            fresh = Fix(
                symptom=fix.symptom,
                diagnosis=fix.diagnosis,
                changed_paths=[f"/work/app/{source_id}.py"],
                verified_by=fix.verified_by,
            )
            await remember_fix(KnowledgeRepository(conn), fresh, source_id=source_id, wiki_id=WIKI)

    with patch.object(fixes_mod, "_recurrence_of", new=slow_lookup):
        results = await asyncio.gather(*(one(s) for s in sources), return_exceptions=True)

    assert [r for r in results if isinstance(r, BaseException)] == []
    async with sqlite_mod.get_db() as conn:
        stored = await KnowledgeRepository(conn).list_objects(kind="fix", scope=SCOPE, limit=100)
    assert len(stored) == 1
    [atom] = stored
    assert atom.properties["occurrences"] == len(sources)
    assert sorted(c.source_id for c in atom.citations) == sources
    assert sorted(atom.properties["changed_paths"]) == sorted(f"/work/app/{s}.py" for s in sources)
