"""Shared pytest fixtures for Archivum tests."""

from __future__ import annotations

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
