from __future__ import annotations

import aiosqlite

# One row per linked client on one machine. `key_hash` rather than the key for
# the same reason `refresh_tokens` and share links store hashes: a leaked
# database should not hand over working access to every machine ever paired.
SCHEMA = """
CREATE TABLE IF NOT EXISTS device_keys (
    id           TEXT PRIMARY KEY,
    wiki_id      TEXT NOT NULL DEFAULT 'default',
    name         TEXT NOT NULL,
    key_hash     TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT,
    revoked_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_device_keys_hash ON device_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_device_keys_wiki ON device_keys(wiki_id);

CREATE TABLE IF NOT EXISTS pairing_tokens (
    id          TEXT PRIMARY KEY,
    wiki_id     TEXT NOT NULL DEFAULT 'default',
    secret_hash TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    expires_at  TEXT NOT NULL,
    redeemed_at TEXT,
    device_id   TEXT REFERENCES device_keys(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_pairing_tokens_secret ON pairing_tokens(secret_hash);

-- Reusable, unlike `pairing_tokens`, because the caller is an agent setting up
-- a machine nobody is watching rather than a person copying a string. It pays
-- for that reach by being usable at exactly one endpoint: it mints device keys
-- and authenticates nothing.
CREATE TABLE IF NOT EXISTS provisioning_tokens (
    id           TEXT PRIMARY KEY,
    wiki_id      TEXT NOT NULL DEFAULT 'default',
    name         TEXT NOT NULL DEFAULT '',
    secret_hash  TEXT NOT NULL UNIQUE,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    -- NULL means no expiry. A token living in dotfiles that dies silently at
    -- midnight is worse than one the owner decided to keep.
    expires_at   TEXT,
    device_cap   INTEGER NOT NULL DEFAULT 25,
    last_used_at TEXT,
    revoked_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_provisioning_tokens_secret
    ON provisioning_tokens(secret_hash);
"""

# Added after `device_keys` shipped, so they arrive by ALTER on existing
# databases. `provisioned_by` is what makes the device cap countable and lets a
# revoked token take its devices with it; `fingerprint` is what stops a machine
# that reinstalls from holding two live keys.
_DEVICE_KEY_COLUMNS = {
    "provisioned_by": "TEXT",
    "fingerprint": "TEXT",
}


async def init_devices_schema(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA)
    async with conn.execute("PRAGMA table_info(device_keys)") as cursor:
        existing = {row[1] for row in await cursor.fetchall()}
    for column, definition in _DEVICE_KEY_COLUMNS.items():
        if column not in existing:
            await conn.execute(f"ALTER TABLE device_keys ADD COLUMN {column} {definition}")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_device_keys_fingerprint "
        "ON device_keys(provisioned_by, fingerprint)"
    )
    await conn.commit()
