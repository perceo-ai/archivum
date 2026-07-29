import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.capture.schema import Conversation, ToolCall, Turn
from archivum.capture.store import CaptureResult, CaptureStore
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return CaptureStore(store=SourceStore(), blob_store=BlobStore(settings.blob_dir),
                        settings=settings)


def _conv():
    tc = ToolCall(name="Edit", arguments={"p": "/a"}, result="written")
    return Conversation(
        session_id="s1", interface="claude_code_native", started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="do X", ts="t"),
               Turn(role="assistant", text="did X", ts="t", tool_calls=(tc,))),
    )


@pytest.mark.asyncio
async def test_capture_writes_source_document_and_chunk_per_turn(env):
    res = await env.capture(_conv())
    assert isinstance(res, CaptureResult)
    assert res.deduplicated is False
    assert res.version == 1
    assert len(res.chunk_ids) == 2
    assert len(res.content_hash) == 64

    store = SourceStore()
    source = await store.get_source(res.source_id)
    assert source is not None and source.source_type.value == "conversation"
    document = await store.get_document_for_source(res.source_id)
    assert document is not None and document.mime == "text/plain"


@pytest.mark.asyncio
async def test_recapture_identical_content_is_dedup_noop(env):
    r1 = await env.capture(_conv())
    r2 = await env.capture(_conv())
    assert r2.deduplicated is True
    assert r2.source_id == r1.source_id
    assert r2.chunk_ids == r1.chunk_ids

    async with __import__("archivum.db.sqlite", fromlist=["get_db"]).get_db() as db:
        async with db.execute("SELECT COUNT(*) AS n FROM chunks") as cur:
            n = (await cur.fetchone())["n"]
    assert n == 2  # not duplicated


@pytest.mark.asyncio
async def test_changed_content_creates_v2_without_mutating_v1(env):
    r1 = await env.capture(_conv())
    changed = Conversation(
        session_id="s1", interface="claude_code_native", started_at="2026-07-28T00:00:00Z",
        turns=(Turn(role="user", text="do Y", ts="t"),),
    )
    r2 = await env.capture(changed)
    assert (r1.version, r2.version) == (1, 2)
    assert r1.content_hash != r2.content_hash
    assert r2.source_id != r1.source_id
