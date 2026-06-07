"""Tests for archivum.db.sqlite — all DB calls mocked via get_db patch."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

import archivum.db.sqlite as sqlite_mod


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_mock_db(
    fetchone_result=None,
    fetchall_result=None,
    lastrowid: int = 1,
    rowcount: int = 1,
):
    """Build a (mock_conn, mock_cursor, mock_get_db) triple."""
    mock_cursor = AsyncMock()
    mock_cursor.fetchone = AsyncMock(return_value=fetchone_result)
    mock_cursor.fetchall = AsyncMock(return_value=fetchall_result or [])
    mock_cursor.lastrowid = lastrowid
    mock_cursor.rowcount = rowcount

    mock_cursor_cm = AsyncMock()
    mock_cursor_cm.__aenter__ = AsyncMock(return_value=mock_cursor)
    mock_cursor_cm.__aexit__ = AsyncMock(return_value=False)

    mock_conn = AsyncMock()
    mock_conn.execute = MagicMock(return_value=mock_cursor_cm)
    mock_conn.commit = AsyncMock()

    @asynccontextmanager
    async def mock_get_db():
        yield mock_conn

    return mock_conn, mock_cursor, mock_get_db


def make_page_row(**overrides) -> dict:
    """Return a dict that acts as a page row (dict(row) works since it IS a dict)."""
    base = {
        "id": 1,
        "wiki_id": "default",
        "slug": "test-slug",
        "title": "Test Page",
        "content": "Some content",
        "tags": "[]",
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "authored_by": "agent",
    }
    base.update(overrides)
    return base


def make_user_row(**overrides) -> dict:
    base = {
        "id": 1,
        "wiki_id": "default",
        "username": "testuser",
        "password_hash": "hashed",
        "role": "viewer",
        "created_at": "2024-01-01T00:00:00",
    }
    base.update(overrides)
    return base


# ── TestGetUserByUsername ─────────────────────────────────────────────────────


class TestGetUserByUsername:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        _, _, mock_get_db = make_mock_db(fetchone_result=None)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_user_by_username("nobody")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        row = make_user_row(username="alice")
        _, _, mock_get_db = make_mock_db(fetchone_result=row)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_user_by_username("alice")
        assert result is not None
        assert result["username"] == "alice"


# ── TestCreateUser ────────────────────────────────────────────────────────────


class TestCreateUser:
    @pytest.mark.asyncio
    async def test_returns_lastrowid(self):
        mock_cursor = AsyncMock()
        mock_cursor.lastrowid = 42

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.create_user("bob", "hash123", "viewer")
        assert result == 42

    @pytest.mark.asyncio
    async def test_executes_insert_query(self):
        mock_cursor = AsyncMock()
        mock_cursor.lastrowid = 1

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            await sqlite_mod.create_user("bob", "hash123", "viewer", "mywiki")

        mock_conn.execute.assert_called_once()
        sql_arg = mock_conn.execute.call_args[0][0]
        assert "INSERT INTO users" in sql_arg


# ── TestUpsertPage ────────────────────────────────────────────────────────────


def make_select_cm(fetchone_result):
    """Build an async context manager that yields a cursor with a given fetchone result."""
    select_inner = AsyncMock()
    select_inner.fetchone = AsyncMock(return_value=fetchone_result)
    select_cm = AsyncMock()
    select_cm.__aenter__ = AsyncMock(return_value=select_inner)
    select_cm.__aexit__ = AsyncMock(return_value=False)
    return select_cm


def make_awaitable_cursor(lastrowid: int = 1, rowcount: int = 1):
    """Return a coroutine that resolves to a cursor mock (for plain await db.execute(...))."""
    cursor = MagicMock()
    cursor.lastrowid = lastrowid
    cursor.rowcount = rowcount

    async def _coro(*_args, **_kwargs):
        return cursor

    return _coro


class TestUpsertPage:
    @pytest.mark.asyncio
    async def test_creates_new_page(self):
        """When no existing row is found, an INSERT is performed."""
        select_cm = make_select_cm(fetchone_result=None)
        insert_coro = make_awaitable_cursor(lastrowid=5)

        mock_conn = MagicMock()
        mock_conn.commit = AsyncMock()
        mock_conn.execute = MagicMock(side_effect=[select_cm, insert_coro()])

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            page_id, created = await sqlite_mod.upsert_page(
                "new-slug", "New Page", "Content", ["tag1"]
            )
        assert created is True
        assert page_id == 5

    @pytest.mark.asyncio
    async def test_updates_existing_page(self):
        """When an existing row is found, an UPDATE is performed."""
        existing_row = {"id": 7}
        select_cm = make_select_cm(fetchone_result=existing_row)
        update_coro = make_awaitable_cursor()

        mock_conn = MagicMock()
        mock_conn.commit = AsyncMock()
        mock_conn.execute = MagicMock(side_effect=[select_cm, update_coro()])

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            page_id, created = await sqlite_mod.upsert_page(
                "existing-slug", "Updated Title", "New content", []
            )
        assert created is False
        assert page_id == 7

    @pytest.mark.asyncio
    async def test_returns_created_true_for_new(self):
        select_cm = make_select_cm(fetchone_result=None)
        insert_coro = make_awaitable_cursor(lastrowid=99)

        mock_conn = MagicMock()
        mock_conn.commit = AsyncMock()
        mock_conn.execute = MagicMock(side_effect=[select_cm, insert_coro()])

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            _, created = await sqlite_mod.upsert_page("s", "T", "C", [])
        assert created is True

    @pytest.mark.asyncio
    async def test_returns_created_false_for_update(self):
        existing_row = {"id": 3}
        select_cm = make_select_cm(fetchone_result=existing_row)
        update_coro = make_awaitable_cursor()

        mock_conn = MagicMock()
        mock_conn.commit = AsyncMock()
        mock_conn.execute = MagicMock(side_effect=[select_cm, update_coro()])

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            _, created = await sqlite_mod.upsert_page("s", "T", "C", [])
        assert created is False


# ── TestGetPage ───────────────────────────────────────────────────────────────


class TestGetPage:
    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        _, _, mock_get_db = make_mock_db(fetchone_result=None)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_page("missing-slug")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_dict_when_found(self):
        row = make_page_row(slug="found-slug")
        _, _, mock_get_db = make_mock_db(fetchone_result=row)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_page("found-slug")
        assert result is not None
        assert result["slug"] == "found-slug"


# ── TestGetPages ──────────────────────────────────────────────────────────────


class TestGetPages:
    @pytest.mark.asyncio
    async def test_returns_empty_for_empty_slugs(self):
        # Should short-circuit without hitting the DB at all.
        with patch("archivum.db.sqlite.get_db", side_effect=AssertionError("get_db should not be called")):
            result = await sqlite_mod.get_pages([])
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_pages_in_slug_order(self):
        rows = [
            {"id": 2, "slug": "b-page", "title": "B", "content": "", "tags": "[]",
             "created_at": "2024-01-01", "updated_at": "2024-01-01", "authored_by": "agent"},
            {"id": 1, "slug": "a-page", "title": "A", "content": "", "tags": "[]",
             "created_at": "2024-01-01", "updated_at": "2024-01-01", "authored_by": "agent"},
        ]
        _, _, mock_get_db = make_mock_db(fetchall_result=rows)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_pages(["a-page", "b-page"])
        # Result should follow the requested slug order.
        assert [r["slug"] for r in result] == ["a-page", "b-page"]


# ── TestDeletePage ────────────────────────────────────────────────────────────


class TestDeletePage:
    @pytest.mark.asyncio
    async def test_returns_true_when_deleted(self):
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 1

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.delete_page("some-slug")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_not_found(self):
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 0

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.delete_page("nonexistent-slug")
        assert result is False


# ── TestSearchPagesFts ────────────────────────────────────────────────────────


class TestSearchPagesFts:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        _, _, mock_get_db = make_mock_db(fetchall_result=[])
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.search_pages_fts("nothing here")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_results_from_db(self):
        rows = [
            {"slug": "r1", "title": "Result One", "tags": "[]", "excerpt": "...text...", "rank": -1.0},
            {"slug": "r2", "title": "Result Two", "tags": "[]", "excerpt": "...more...", "rank": -0.5},
        ]
        _, _, mock_get_db = make_mock_db(fetchall_result=rows)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.search_pages_fts("keyword")
        assert len(result) == 2
        assert result[0]["slug"] == "r1"


# ── TestShareLinks ────────────────────────────────────────────────────────────


class TestShareLinks:
    @pytest.mark.asyncio
    async def test_create_share_link_returns_id(self):
        mock_cursor = AsyncMock()
        mock_cursor.lastrowid = 10

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.create_share_link("tok123", "page", "some-slug", None)
        assert result == 10

    @pytest.mark.asyncio
    async def test_get_share_link_returns_none_when_not_found(self):
        _, _, mock_get_db = make_mock_db(fetchone_result=None)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_share_link("missing-token")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_share_link_returns_none_when_expired(self):
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        row = {
            "id": 1, "wiki_id": "default", "token": "expired-tok",
            "type": "page", "target_id": "slug", "created_at": "2024-01-01",
            "expires_at": past, "revoked": 0,
        }
        _, _, mock_get_db = make_mock_db(fetchone_result=row)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_share_link("expired-tok")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_share_link_returns_dict_when_valid(self):
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        row = {
            "id": 1, "wiki_id": "default", "token": "valid-tok",
            "type": "page", "target_id": "slug", "created_at": "2024-01-01",
            "expires_at": future, "revoked": 0,
        }
        _, _, mock_get_db = make_mock_db(fetchone_result=row)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_share_link("valid-tok")
        assert result is not None
        assert result["token"] == "valid-tok"

    @pytest.mark.asyncio
    async def test_revoke_share_link(self):
        mock_cursor = AsyncMock()
        mock_cursor.rowcount = 1

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.revoke_share_link("tok123")
        assert result is True


# ── TestIngestLog ─────────────────────────────────────────────────────────────


class TestIngestLog:
    @pytest.mark.asyncio
    async def test_create_ingest_log_returns_id(self):
        mock_cursor = AsyncMock()
        mock_cursor.lastrowid = 7

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.create_ingest_log("file", "/some/path.md")
        assert result == 7

    @pytest.mark.asyncio
    async def test_update_ingest_log_calls_execute(self):
        mock_conn = AsyncMock()
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            await sqlite_mod.update_ingest_log(3, "done", pages_created=2, pages_updated=1)

        mock_conn.execute.assert_called_once()
        sql_arg = mock_conn.execute.call_args[0][0]
        assert "UPDATE ingest_log" in sql_arg


# ── TestRefreshTokens ─────────────────────────────────────────────────────────


class TestRefreshTokens:
    @pytest.mark.asyncio
    async def test_store_refresh_token(self):
        mock_conn = AsyncMock()
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            # Should not raise.
            await sqlite_mod.store_refresh_token(1, "hash_abc", "2025-01-01T00:00:00")

        mock_conn.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_refresh_token_returns_none(self):
        _, _, mock_get_db = make_mock_db(fetchone_result=None)
        with patch("archivum.db.sqlite.get_db", mock_get_db):
            result = await sqlite_mod.get_refresh_token("unknown-hash")
        assert result is None

    @pytest.mark.asyncio
    async def test_revoke_refresh_token(self):
        mock_conn = AsyncMock()
        mock_conn.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            await sqlite_mod.revoke_refresh_token("hash_abc")

        mock_conn.execute.assert_called_once()
        sql_arg = mock_conn.execute.call_args[0][0]
        assert "revoked=1" in sql_arg


# ── TestEnsureOwnerExists ─────────────────────────────────────────────────────


class TestEnsureOwnerExists:
    @pytest.mark.asyncio
    async def test_skips_if_owner_already_exists(self):
        """If an owner row is found, no INSERT should be made."""
        existing_owner = {"id": 1}

        select_inner = AsyncMock()
        select_inner.fetchone = AsyncMock(return_value=existing_owner)
        select_cm = AsyncMock()
        select_cm.__aenter__ = AsyncMock(return_value=select_inner)
        select_cm.__aexit__ = AsyncMock(return_value=False)

        mock_conn = AsyncMock()
        mock_conn.commit = AsyncMock()
        # Return the select context manager; second call should never happen.
        mock_conn.execute = MagicMock(return_value=select_cm)

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            await sqlite_mod.ensure_owner_exists("admin", "hash")

        # Only the SELECT should have been executed, no INSERT.
        assert mock_conn.execute.call_count == 1
        mock_conn.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_owner_if_none(self):
        """If no owner exists, an INSERT should be performed."""
        select_cm = make_select_cm(fetchone_result=None)
        insert_coro = make_awaitable_cursor()

        mock_conn = MagicMock()
        mock_conn.commit = AsyncMock()
        mock_conn.execute = MagicMock(side_effect=[select_cm, insert_coro()])

        @asynccontextmanager
        async def mock_get_db():
            yield mock_conn

        with patch("archivum.db.sqlite.get_db", mock_get_db):
            await sqlite_mod.ensure_owner_exists("admin", "hash")

        assert mock_conn.execute.call_count == 2
        mock_conn.commit.assert_called_once()
