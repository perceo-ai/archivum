from pathlib import Path

import pytest

import archivum.db.sqlite as sqlite_mod
from archivum.capture.importers.chatgpt import ChatGptImporter
from archivum.capture.importers.claude_code import ClaudeCodeImporter
from archivum.capture.native import NativeCaptureWriter
from archivum.capture.store import CaptureStore
from archivum.config import Settings
from archivum.db.sqlite import get_db
from archivum.store.blobs import BlobStore
from archivum.store.repository import SourceStore

FIXDIR = Path(__file__).parent.parent / "fixtures" / "capture"
SECRETS = ("internal plan", "hidden reasoning", "secret chain")


@pytest.fixture
async def env(tmp_path):
    settings = Settings(db_path=tmp_path / "archivum.db", blob_dir=tmp_path / "blobs")
    await sqlite_mod.init_db(settings)
    store = CaptureStore(store=SourceStore(), blob_store=BlobStore(settings.blob_dir),
                         settings=settings)
    return settings, store


async def _counts():
    async with get_db() as db:
        out = {}
        for t in ("sources", "documents", "chunks"):
            async with db.execute(f"SELECT COUNT(*) AS n FROM {t}") as cur:
                out[t] = (await cur.fetchone())["n"]
        return out


@pytest.mark.asyncio
async def test_reimport_is_a_noop(env):
    _, store = env
    conv = ClaudeCodeImporter().parse(FIXDIR / "claude_code_session.jsonl").conversations[0]
    await store.capture(conv)
    first = await _counts()
    assert first["sources"] >= 1 and first["chunks"] >= 1
    again = ClaudeCodeImporter().parse(FIXDIR / "claude_code_session.jsonl").conversations[0]
    await store.capture(again)
    assert await _counts() == first


@pytest.mark.asyncio
async def test_no_hidden_reasoning_from_any_source(env):
    settings, store = env
    await store.capture(ClaudeCodeImporter().parse(FIXDIR / "claude_code_session.jsonl").conversations[0])
    await store.capture(ChatGptImporter().parse(FIXDIR / "chatgpt_export.json").conversations[0])
    w = NativeCaptureWriter(store, session_id="native1")
    w.record_turn("assistant", "<thinking>secret chain</thinking> ok")
    await w.flush()

    # L0 blobs hold canonical JSON — verify no secret survived into any blob.
    blobs = BlobStore(settings.blob_dir)
    async with get_db() as db:
        async with db.execute("SELECT content_hash FROM sources") as cur:
            hashes = [r["content_hash"] for r in await cur.fetchall()]
    assert len(hashes) >= 3
    corpus = " ".join(blobs.get(h).decode("utf-8") for h in hashes)
    for secret in SECRETS:
        assert secret not in corpus
