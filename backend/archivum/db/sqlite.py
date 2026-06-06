"""aiosqlite wrapper — schema init and CRUD for all tables."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, AsyncGenerator

import aiosqlite

from archivum.config import Settings, get_settings

# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT    NOT NULL DEFAULT 'default',
    username    TEXT    NOT NULL UNIQUE,
    password_hash TEXT  NOT NULL,
    role        TEXT    NOT NULL DEFAULT 'viewer',  -- owner|collaborator|viewer
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT    NOT NULL DEFAULT 'default',
    slug        TEXT    NOT NULL,
    title       TEXT    NOT NULL,
    content     TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '[]',   -- JSON array
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    authored_by TEXT    NOT NULL DEFAULT 'agent', -- user|agent
    UNIQUE(wiki_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_pages_wiki ON pages(wiki_id);
CREATE INDEX IF NOT EXISTS idx_pages_slug ON pages(slug);

-- FTS5 virtual table for keyword search
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
    slug,
    title,
    content,
    tags,
    content='pages',
    content_rowid='id'
);

-- Keep FTS in sync
CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
    INSERT INTO pages_fts(rowid, slug, title, content, tags)
    VALUES (new.id, new.slug, new.title, new.content, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, slug, title, content, tags)
    VALUES ('delete', old.id, old.slug, old.title, old.content, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS pages_au AFTER UPDATE ON pages BEGIN
    INSERT INTO pages_fts(pages_fts, rowid, slug, title, content, tags)
    VALUES ('delete', old.id, old.slug, old.title, old.content, old.tags);
    INSERT INTO pages_fts(rowid, slug, title, content, tags)
    VALUES (new.id, new.slug, new.title, new.content, new.tags);
END;

CREATE TABLE IF NOT EXISTS share_links (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id     TEXT    NOT NULL DEFAULT 'default',
    token       TEXT    NOT NULL UNIQUE,
    type        TEXT    NOT NULL DEFAULT 'page',  -- page|query
    target_id   TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ingest_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id         TEXT    NOT NULL DEFAULT 'default',
    source_type     TEXT    NOT NULL,  -- file|url|batch
    source_path     TEXT    NOT NULL,
    status          TEXT    NOT NULL DEFAULT 'pending',  -- pending|running|done|error
    pages_created   INTEGER NOT NULL DEFAULT 0,
    pages_updated   INTEGER NOT NULL DEFAULT 0,
    error           TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash  TEXT    NOT NULL UNIQUE,
    expires_at  TEXT    NOT NULL,
    revoked     INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_refresh_tokens_hash ON refresh_tokens(token_hash);

CREATE TABLE IF NOT EXISTS invite_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    wiki_id    TEXT    NOT NULL DEFAULT 'default',
    token      TEXT    NOT NULL UNIQUE,
    role       TEXT    NOT NULL DEFAULT 'viewer',  -- collaborator|viewer
    created_by TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    expires_at TEXT,
    used       INTEGER NOT NULL DEFAULT 0
);
"""


# ── Connection factory ────────────────────────────────────────────────────────

_db_path: Path | None = None


def configure(settings: Settings) -> None:
    global _db_path
    _db_path = settings.db_path
    _db_path.parent.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def get_db() -> AsyncGenerator[aiosqlite.Connection, None]:
    settings = get_settings()
    path = _db_path or settings.db_path
    async with aiosqlite.connect(str(path)) as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        yield conn


# ── Schema init ───────────────────────────────────────────────────────────────

async def init_db(settings: Settings) -> None:
    configure(settings)
    async with get_db() as db:
        await db.executescript(_SCHEMA)
        await db.commit()


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user_by_username(username: str) -> dict[str, Any] | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def create_user(
    username: str,
    password_hash: str,
    role: str = "viewer",
    wiki_id: str = "default",
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO users (wiki_id, username, password_hash, role) VALUES (?,?,?,?)",
            (wiki_id, username, password_hash, role),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def ensure_owner_exists(username: str, password_hash: str) -> None:
    """Create the owner account if it doesn't already exist."""
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM users WHERE role='owner' LIMIT 1"
        ) as cur:
            row = await cur.fetchone()
        if row:
            return
        await db.execute(
            "INSERT INTO users (wiki_id, username, password_hash, role) VALUES ('default',?,?,'owner')",
            (username, password_hash),
        )
        await db.commit()


# ── Pages ─────────────────────────────────────────────────────────────────────

async def list_pages(wiki_id: str = "default") -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(
            "SELECT id, wiki_id, slug, title, tags, created_at, updated_at, authored_by "
            "FROM pages WHERE wiki_id=? ORDER BY updated_at DESC",
            (wiki_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


async def get_page(slug: str, wiki_id: str = "default") -> dict[str, Any] | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM pages WHERE slug=? AND wiki_id=?",
            (slug, wiki_id),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def get_pages(
    slugs: list[str],
    wiki_id: str = "default",
) -> list[dict[str, Any]]:
    """Batch-get pages by slug to avoid N+1 query patterns.

    Returns results in the same order as `slugs` (deduplicated, first occurrence wins).
    """

    if not slugs:
        return []

    # Deduplicate while preserving order.
    ordered_slugs: list[str] = []
    seen: set[str] = set()
    for s in slugs:
        if s not in seen:
            seen.add(s)
            ordered_slugs.append(s)

    placeholders = ",".join(["?" for _ in ordered_slugs])
    sql = (
        f"SELECT id, slug, title, content, tags, created_at, updated_at, authored_by "
        f"FROM pages WHERE wiki_id=? AND slug IN ({placeholders})"
    )

    async with get_db() as db:
        async with db.execute(sql, (wiki_id, *ordered_slugs)) as cur:
            rows = await cur.fetchall()

    by_slug: dict[str, dict[str, Any]] = {r["slug"]: dict(r) for r in rows}
    return [by_slug[s] for s in ordered_slugs if s in by_slug]


async def upsert_page(
    slug: str,
    title: str,
    content: str,
    tags: list[str],
    authored_by: str = "agent",
    wiki_id: str = "default",
) -> tuple[int, bool]:
    """Return (id, created) where created=True means a new row was inserted."""
    tags_json = json.dumps(tags)
    now = datetime.now(UTC).isoformat()
    async with get_db() as db:
        async with db.execute(
            "SELECT id FROM pages WHERE slug=? AND wiki_id=?", (slug, wiki_id)
        ) as cur:
            row = await cur.fetchone()

        if row:
            await db.execute(
                "UPDATE pages SET title=?, content=?, tags=?, updated_at=?, authored_by=? "
                "WHERE slug=? AND wiki_id=?",
                (title, content, tags_json, now, authored_by, slug, wiki_id),
            )
            await db.commit()
            return row["id"], False
        else:
            cur = await db.execute(
                "INSERT INTO pages (wiki_id, slug, title, content, tags, authored_by) "
                "VALUES (?,?,?,?,?,?)",
                (wiki_id, slug, title, content, tags_json, authored_by),
            )
            await db.commit()
            return cur.lastrowid, True  # type: ignore[return-value]


async def delete_page(slug: str, wiki_id: str = "default") -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "DELETE FROM pages WHERE slug=? AND wiki_id=?", (slug, wiki_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def search_pages_fts(
    query: str, wiki_id: str = "default", limit: int = 10
) -> list[dict[str, Any]]:
    """Full-text search using FTS5. Returns rows with a snippet."""
    async with get_db() as db:
        async with db.execute(
            """
            SELECT p.slug, p.title, p.tags,
                   snippet(pages_fts, 2, '<mark>', '</mark>', '…', 20) AS excerpt,
                   rank
            FROM pages_fts
            JOIN pages p ON p.id = pages_fts.rowid
            WHERE pages_fts MATCH ? AND p.wiki_id = ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, wiki_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ── Share links ───────────────────────────────────────────────────────────────

async def create_share_link(
    token: str,
    link_type: str,
    target_id: str | None,
    expires_at: str | None,
    wiki_id: str = "default",
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO share_links (wiki_id, token, type, target_id, expires_at) "
            "VALUES (?,?,?,?,?)",
            (wiki_id, token, link_type, target_id, expires_at),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def get_share_link(token: str) -> dict[str, Any] | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM share_links WHERE token=? AND revoked=0",
            (token,),
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return None

            data = dict(row)
            expires_at = data.get("expires_at")
            if expires_at:
                try:
                    exp = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=UTC)
                    if exp <= datetime.now(UTC):
                        return None
                except Exception:
                    # If we can't parse expires_at, fall back to serving it.
                    pass

            return data


async def revoke_share_link(token: str) -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "UPDATE share_links SET revoked=1 WHERE token=?", (token,)
        )
        await db.commit()
        return cur.rowcount > 0


async def list_share_links(wiki_id: str = "default") -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM share_links WHERE wiki_id=? ORDER BY created_at DESC",
            (wiki_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ── Ingest log ────────────────────────────────────────────────────────────────

async def create_ingest_log(
    source_type: str,
    source_path: str,
    wiki_id: str = "default",
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "INSERT INTO ingest_log (wiki_id, source_type, source_path, status) VALUES (?,?,?,'running')",
            (wiki_id, source_type, source_path),
        )
        await db.commit()
        return cur.lastrowid  # type: ignore[return-value]


async def update_ingest_log(
    log_id: int,
    status: str,
    pages_created: int = 0,
    pages_updated: int = 0,
    error: str | None = None,
) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE ingest_log SET status=?, pages_created=?, pages_updated=?, error=? WHERE id=?",
            (status, pages_created, pages_updated, error, log_id),
        )
        await db.commit()


async def list_ingest_logs(wiki_id: str = "default", limit: int = 50) -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM ingest_log WHERE wiki_id=? ORDER BY created_at DESC LIMIT ?",
            (wiki_id, limit),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]


# ── Refresh tokens ────────────────────────────────────────────────────────────

async def store_refresh_token(
    user_id: int,
    token_hash: str,
    expires_at: str,
) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO refresh_tokens (user_id, token_hash, expires_at) VALUES (?,?,?)",
            (user_id, token_hash, expires_at),
        )
        await db.commit()


async def get_refresh_token(token_hash: str) -> dict[str, Any] | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT rt.*, u.username, u.role, u.wiki_id FROM refresh_tokens rt "
            "JOIN users u ON u.id = rt.user_id "
            "WHERE rt.token_hash=? AND rt.revoked=0",
            (token_hash,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def revoke_refresh_token(token_hash: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE refresh_tokens SET revoked=1 WHERE token_hash=?", (token_hash,)
        )
        await db.commit()


async def revoke_all_refresh_tokens(user_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,)
        )
        await db.commit()


# ── Invite tokens ─────────────────────────────────────────────────────────────

async def create_invite_token(
    wiki_id: str,
    token: str,
    role: str,
    created_by: str,
    expires_at: str | None,
) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT INTO invite_tokens (wiki_id, token, role, created_by, expires_at) VALUES (?,?,?,?,?)",
            (wiki_id, token, role, created_by, expires_at),
        )
        await db.commit()


async def get_invite_token(token: str) -> dict[str, Any] | None:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM invite_tokens WHERE token=?", (token,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


async def mark_invite_used(token: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE invite_tokens SET used=1 WHERE token=?", (token,)
        )
        await db.commit()


async def list_invite_tokens(wiki_id: str = "default") -> list[dict[str, Any]]:
    async with get_db() as db:
        async with db.execute(
            "SELECT * FROM invite_tokens WHERE wiki_id=? ORDER BY created_at DESC",
            (wiki_id,),
        ) as cur:
            rows = await cur.fetchall()
            return [dict(r) for r in rows]
