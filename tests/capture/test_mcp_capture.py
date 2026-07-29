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
