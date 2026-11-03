"""Shared pytest fixtures for Archivum tests."""


from __future__ import annotations

# The app's background workers stay off for the whole suite, set before any
# `archivum` import reads the environment.
#
# Every test that enters a `TestClient` context runs the real lifespan, which
# starts six workers against that test's own paths. They are not leaked —
# shutdown cancels and awaits each one, measured — but while the test runs they
# do real work: polling queues, sweeping the vault, reaching for a model.
#
# Idle workers cost nothing measurable, which is why this never showed up.
# Once capture began queueing distillation on every path that captures, the
# work became real, and `tests/api` went from 78 seconds to over eighteen
# minutes while every file in it still passed in seconds on its own.
#
# `RETENTION_SWEEP_ENABLED` is the retention worker's actual flag name; a guess
# at `RETENTION_WORKER_ENABLED` would be silently ignored, because pydantic
# settings take the field name and an unknown variable is simply not read.
#
# A test that wants a worker sets its flag and starts it itself.
import os

for _flag in (
    "DISTILL_WORKER_ENABLED",
    "PAGE_WRITE_WORKER_ENABLED",
    "RETENTION_SWEEP_ENABLED",
    "CODE_REPO_WORKER_ENABLED",
    "SUMMARY_WORKER_ENABLED",
    "TRANSCRIPT_WATCH_ENABLED",
    "VAULT_WATCH_ENABLED",
):
    os.environ.setdefault(_flag, "false")

import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient


# ── LLM response fixture ──────────────────────────────────────────────────────


@pytest.fixture
def mock_llm_response():
    """A valid LLM extraction JSON response dict."""
    return {
        "pages": [
            {
                "slug": "test-page",
                "title": "Test Page",
                "content": "---\ntitle: Test Page\ntags: [test]\n---\n\n# Test Page\n\nContent with [[Entity One]].",
                "tags": ["test"],
            }
        ],
        "entities": [
            {"name": "Entity One", "type": "concept"},
            {"name": "Entity Two", "type": "person"},
        ],
        "relationships": [
            {"from": "Entity One", "to": "Entity Two", "type": "related_to"}
        ],
    }


# ── Kuzu graph fixture ────────────────────────────────────────────────────────


@pytest.fixture
def mock_kuzu_conn():
    """Patches archivum.db.graph._get_conn with a MagicMock connection.

    The mock connection's .execute() returns a mock result whose
    .has_next() returns False by default (no rows).
    """
    mock_result = MagicMock()
    mock_result.has_next.return_value = False

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result

    with patch("archivum.db.graph._get_conn", return_value=mock_conn):
        yield mock_conn


# ── Qdrant client fixture ─────────────────────────────────────────────────────


@pytest.fixture
def mock_qdrant_client():
    """Patches archivum.db.qdrant_client.AsyncQdrantClient with an AsyncMock."""
    mock_collections = MagicMock()
    mock_collections.collections = []

    mock_instance = AsyncMock()
    mock_instance.upsert.return_value = None
    mock_instance.search.return_value = []
    mock_instance.delete.return_value = None
    mock_instance.get_collections.return_value = mock_collections
    mock_instance.create_collection.return_value = None

    with patch(
        "archivum.db.qdrant_client.AsyncQdrantClient",
        return_value=mock_instance,
    ):
        yield mock_instance


# ── Fix vector channel ────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fix_vectors_offline():
    """Keep the fix vector channel away from live services, in every test.

    The first run of this channel proved why: a developer machine with Qdrant
    and the embedding model running had test fixes embedded into its real
    collection, and an unrelated-error test then failed because the live model
    genuinely scored the query above the floor. Tests that want the channel
    patch these targets themselves; everything else gets silence, which is
    also what a machine without Qdrant gets.
    """
    with (
        patch("archivum.db.qdrant_client.upsert_fix", new=AsyncMock()),
        patch("archivum.db.qdrant_client.search_fixes", new=AsyncMock(return_value=[])),
    ):
        yield


# ── SQLite fixture ────────────────────────────────────────────────────────────


@pytest.fixture
def mock_sqlite_db():
    """Patches archivum.db.sqlite.aiosqlite.connect with an AsyncMock.

    The mock works as an async context manager that yields a mock connection
    with stubbed execute, executescript, and commit.
    """
    mock_cursor = AsyncMock()
    mock_cursor.fetchone.return_value = None
    mock_cursor.fetchall.return_value = []
    mock_cursor.lastrowid = 1
    mock_cursor.rowcount = 1

    # cursor is returned by execute() which is used as async context manager
    mock_cursor_cm = AsyncMock()
    mock_cursor_cm.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor_cm.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute.return_value = mock_cursor_cm
    mock_conn.executescript = AsyncMock()
    mock_conn.commit = AsyncMock()
    # Allow row_factory to be set
    mock_conn.row_factory = None

    # aiosqlite.connect() is used as: async with aiosqlite.connect(...) as conn:
    mock_connect_cm = AsyncMock()
    mock_connect_cm.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_connect_cm.__aexit__ = AsyncMock(return_value=False)

    with patch("archivum.db.sqlite.aiosqlite.connect", return_value=mock_connect_cm):
        yield mock_conn


# ── App TestClient fixture ────────────────────────────────────────────────────


@pytest.fixture
def app_client(mock_kuzu_conn, mock_qdrant_client, mock_sqlite_db):
    """Creates a FastAPI TestClient with all external systems patched."""
    extra_patches = [
        patch("archivum.main.sqlite.init_db", new=AsyncMock()),
        patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
        patch("archivum.main.graph.init_graph", new=AsyncMock()),
        patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
    ]

    with contextlib.ExitStack() as stack:
        for p in extra_patches:
            stack.enter_context(p)

        from archivum.main import create_app

        test_app = create_app()
        client = TestClient(test_app, raise_server_exceptions=True)
        yield client
