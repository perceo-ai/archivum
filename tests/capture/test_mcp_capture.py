import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.config import Settings


@pytest.fixture
async def env(tmp_path, monkeypatch):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    monkeypatch.setattr("archivum.mcp.server.get_settings", lambda: settings)
    return settings


@pytest.mark.asyncio
async def test_capture_conversation_impl_persists_and_redacts(env):
    from archivum.mcp.server import capture_conversation_impl

    out = await capture_conversation_impl(
        session_id="s1", interface="claude_code_native",
        turns=[{"role": "user", "text": "hi"},
               {"role": "assistant", "text": "<thinking>x</thinking> hello"}],
    )
    assert out["deduplicated"] is False
    assert out["chunks"] == 2
    assert len(out["content_hash"]) == 64


@pytest.mark.asyncio
async def test_capture_through_mcp_queues_the_source_for_distillation(env):
    """A Source nothing distills is inert, and this path never queued one.

    The REST `/capture` endpoint has always enqueued. The MCP tool did not, so
    an agent that called `capture_conversation` got a stored conversation that
    could never become a chat asset, a scenario, or a recallable fix.
    """
    from archivum.mcp.server import capture_conversation_impl

    out = await capture_conversation_impl(
        session_id="s-distil",
        turns=[{"role": "user", "text": "why did the retry loop stall"}],
    )

    jobs = await sqlite_mod.list_distillation_jobs("default")
    assert [job["source_id"] for job in jobs] == [out["source_id"]]
    assert jobs[0]["status"] == "pending"
