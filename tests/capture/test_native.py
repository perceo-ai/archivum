import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.capture.native import NativeCaptureWriter
from archivum.capture.store import CaptureStore
from archivum.config import Settings
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore


@pytest.fixture
async def store(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    return CaptureStore(store=SourceStore(), blob_store=BlobStore(settings.blob_dir),
                        settings=settings)


@pytest.mark.asyncio
async def test_native_writer_redacts_records_and_flushes(store):
    w = NativeCaptureWriter(store, session_id="s1")
    w.record_turn("user", "add a feature")
    w.record_turn("assistant", "<thinking>hidden</thinking> on it")
    w.record_tool_call("Edit", {"path": "/a.py"}, "written")
    w.record_decision("use dataclasses", "simpler")
    w.record_outcome("add feature", "success")

    conv = w.build()
    assert "hidden" not in conv.turns[1].text
    assert conv.turns[1].tool_calls[0].name == "Edit"
    assert conv.decisions[0].statement == "use dataclasses"
    assert conv.outcomes[0].status == "success"

    res = await w.flush()
    assert res.deduplicated is False
    assert len(res.chunk_ids) == 2
