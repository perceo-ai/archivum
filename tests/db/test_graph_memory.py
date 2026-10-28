"""The graph owner must not accumulate memory across operations.

It once did, twice over: one kuzu Connection held for the life of the process
kept every statement it had prepared, and the database only checkpointed at a
16 MB WAL, by which point the version state behind it ran to gigabytes. The
backend reached 11.4 GB on a lightly used vault.
"""

from __future__ import annotations

import kuzu
import pytest

import archivum.db.graph as graph
from archivum.config import Settings

_THRESHOLD = 8 * 1024


@pytest.fixture
def owner(tmp_path, monkeypatch):
    settings = Settings(kuzu_path=tmp_path / "kuzu", kuzu_checkpoint_threshold_bytes=_THRESHOLD)
    monkeypatch.setattr(graph, "get_settings", lambda: settings)
    monkeypatch.setattr(graph, "_db", None)
    yield settings
    if graph._db is not None:
        graph._db.close()


async def test_each_operation_gets_its_own_connection_on_one_database(owner):
    await graph.init_graph(owner)
    database = graph._db

    first, second = graph._get_conn(), graph._get_conn()

    # Prepared statements live as long as their connection, so a shared one
    # is a leak; the database, though, must stay the single handle.
    assert first is not second
    assert graph._db is database
    first.close()
    assert second.execute("RETURN 1").get_next() == [1]


def test_database_is_opened_with_the_configured_checkpoint_threshold(owner, monkeypatch):
    opened: list[dict] = []
    real_database = kuzu.Database

    def recording_database(path, **kwargs):
        opened.append(kwargs)
        return real_database(path, **kwargs)

    monkeypatch.setattr(graph.kuzu, "Database", recording_database)
    graph._get_conn(owner)

    assert opened == [{"checkpoint_threshold": _THRESHOLD}]
    # Kuzu's own 16 MB default is what let version state reach gigabytes.
    assert Settings().kuzu_checkpoint_threshold_bytes <= 1024 * 1024


async def test_steady_writes_keep_getting_checkpointed(owner):
    await graph.init_graph(owner)
    wal = owner.kuzu_path / "archivum.kuzu.wal"
    citations = [{"source_id": "s", "quote": "q" * 200}]

    largest = 0
    # ~600 WAL bytes a write: unchecked, 150 of them overshoot the bound 3x.
    for i in range(150):
        # A bounded graph rewritten over and over: the shape of steady capture.
        await graph.upsert_knowledge_node(
            f"n{i % 20}", f"label {i}", "concept", "default", 0.5, "llm", citations
        )
        largest = max(largest, wal.stat().st_size if wal.exists() else 0)

    # Without checkpoints the WAL only grows; with them it keeps resetting.
    assert largest > 0
    assert largest < 4 * _THRESHOLD
