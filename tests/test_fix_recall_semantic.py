"""Recognising the same trouble told in different words.

Lexical overlap answers "have I pasted this exact error before?" and nothing
else. Measured against realistic paraphrases, it missed most of them:
"address already in use when starting archcar" scored 0.33 against a stored
"archcar endpoint already has a live listener" and was dropped. The vector
channel over symptom plus diagnosis is what makes recall answer the question
people actually ask, which is "have I hit this *trouble* before?"

The two channels have different failure modes, so both are tested alone:
lexical must keep answering on a machine where Qdrant is down, and the vector
channel must not resurrect records the repository no longer holds.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import aiosqlite

from archivum.fixes import Fix, fix_to_object, recall_fixes, reindex_fixes
from archivum.knowledge.repository import KnowledgeRepository, init_knowledge_schema

_LISTENER = Fix(
    symptom="archcar endpoint already has a live listener",
    diagnosis="restarting archcar left the old process bound to the socket",
    changed_paths=["services/archcar/main.rs"],
)

_INSTALLER = Fix(
    symptom="silent installer failure",
    diagnosis="install.sh exited 0 when curl was missing, so nothing was installed",
    changed_paths=["install.sh"],
)


async def _store(*fixes_with_ids: tuple[str, Fix]) -> tuple[aiosqlite.Connection, KnowledgeRepository]:
    conn = await aiosqlite.connect(":memory:")
    await init_knowledge_schema(conn)
    repo = KnowledgeRepository(conn)
    for source_id, fix in fixes_with_ids:
        await repo.upsert_object(fix_to_object(fix, source_id=source_id, wiki_id="default"))
    return conn, repo


def _dense(*hits: tuple[str, float]) -> AsyncMock:
    return AsyncMock(return_value=[{"fix_id": fix_id, "score": score} for fix_id, score in hits])


async def test_a_paraphrase_of_the_trouble_finds_the_fix():
    """The words never seen before still land, because the meaning was stored."""
    conn, repo = await _store(("src-1", _LISTENER))
    try:
        with patch("archivum.db.qdrant_client.search_fixes", new=_dense(("fix:src-1", 0.83))):
            found = await recall_fixes(
                repo, symptom="address already in use when starting archcar", wiki_id="default"
            )
        assert [f.id for f in found] == ["fix:src-1"]
    finally:
        await conn.close()


async def test_recall_still_answers_when_qdrant_is_down():
    """Losing the vector channel degrades recall to lexical; it never breaks it."""
    conn, repo = await _store(("src-1", _LISTENER))
    try:
        with patch(
            "archivum.db.qdrant_client.search_fixes",
            new=AsyncMock(side_effect=RuntimeError("connection refused")),
        ):
            found = await recall_fixes(
                repo, symptom="archcar endpoint already has a live listener", wiki_id="default"
            )
        assert [f.id for f in found] == ["fix:src-1"]
    finally:
        await conn.close()


async def test_a_vector_for_a_deleted_record_is_not_resurrected():
    """A Qdrant point can outlive its knowledge object; only the object is truth."""
    conn, repo = await _store(("src-1", _LISTENER))
    try:
        with patch("archivum.db.qdrant_client.search_fixes", new=_dense(("fix:gone", 0.90))):
            found = await recall_fixes(repo, symptom="some deleted trouble", wiki_id="default")
        assert found == []
    finally:
        await conn.close()


async def test_a_ghost_vector_does_not_displace_a_valid_fix():
    """Review finding: the cut to `limit` used to happen before dropping ids
    the repository no longer holds, so a ghost could push a real fix out."""
    conn, repo = await _store(("src-1", _LISTENER))
    try:
        with patch(
            "archivum.db.qdrant_client.search_fixes",
            new=_dense(("fix:gone", 0.95), ("fix:src-1", 0.80)),
        ):
            found = await recall_fixes(
                repo,
                symptom="address already in use when starting archcar",
                wiki_id="default",
                limit=1,
            )
        assert [f.id for f in found] == ["fix:src-1"]
    finally:
        await conn.close()


async def test_dense_scores_below_the_fix_floor_are_noise():
    """Different errors score ~0.6-0.7 against each other; that must not recall."""
    conn, repo = await _store(("src-1", _LISTENER))
    try:
        with patch("archivum.db.qdrant_client.search_fixes", new=_dense(("fix:src-1", 0.65))):
            found = await recall_fixes(
                repo, symptom="ZeroDivisionError: division by zero", wiki_id="default"
            )
        assert found == []
    finally:
        await conn.close()


async def test_agreement_between_channels_outranks_either_alone():
    conn, repo = await _store(("src-1", _LISTENER), ("src-2", _INSTALLER))
    try:
        with patch("archivum.db.qdrant_client.search_fixes", new=_dense(("fix:src-2", 0.80))):
            found = await recall_fixes(
                # Lexically this touches both fixes ("silent...failure" vs the
                # stored symptoms); the vector channel agreeing on src-2 must
                # settle the order.
                repo,
                symptom="silent installer failure",
                wiki_id="default",
            )
        assert found and found[0].id == "fix:src-2"
    finally:
        await conn.close()


async def test_reindex_embeds_every_stored_fix_and_nothing_else():
    """Backfill for stores that predate the vector channel."""
    conn, repo = await _store(("src-1", _LISTENER), ("src-2", _INSTALLER))
    try:
        upserted = AsyncMock()
        with patch("archivum.db.qdrant_client.upsert_fix", new=upserted):
            count = await reindex_fixes(repo, wiki_id="default")
        assert count == 2
        embedded = {call.args[0] for call in upserted.await_args_list}
        assert embedded == {"fix:src-1", "fix:src-2"}
        # The diagnosis travels with the symptom: it is where the other names
        # for the same trouble live.
        texts = {call.args[1:3] for call in upserted.await_args_list}
        assert (_LISTENER.symptom, _LISTENER.diagnosis) in texts
    finally:
        await conn.close()
