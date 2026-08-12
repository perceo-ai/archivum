"""Memory asset registry schema. Applied idempotently at init."""

from __future__ import annotations

MEMORY_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_assets (
    id          TEXT    PRIMARY KEY,
    wiki_id     TEXT    NOT NULL DEFAULT 'default',
    asset_type  TEXT    NOT NULL,
    layer       TEXT    NOT NULL DEFAULT 'L1',
    name        TEXT    NOT NULL,
    owner       TEXT    NOT NULL DEFAULT 'person:self',
    scope       TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'archived')),
    visibility  TEXT    NOT NULL DEFAULT 'private'
                CHECK (visibility IN ('private', 'shared', 'public')),
    version     INTEGER NOT NULL DEFAULT 1,
    page_slug   TEXT,
    summary     TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    tags        TEXT    NOT NULL DEFAULT '[]',
    metadata    TEXT    NOT NULL DEFAULT '{}',
    citations   TEXT    NOT NULL DEFAULT '[]',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_assets_wiki_type
    ON memory_assets(wiki_id, asset_type, status);
CREATE INDEX IF NOT EXISTS idx_memory_assets_scope
    ON memory_assets(scope);
CREATE INDEX IF NOT EXISTS idx_memory_assets_layer
    ON memory_assets(wiki_id, layer);

CREATE TABLE IF NOT EXISTS memory_asset_versions (
    asset_id    TEXT    NOT NULL,
    version     INTEGER NOT NULL,
    name        TEXT    NOT NULL,
    summary     TEXT    NOT NULL DEFAULT '',
    body        TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'draft',
    metadata    TEXT    NOT NULL DEFAULT '{}',
    citations   TEXT    NOT NULL DEFAULT '[]',
    change_note TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (asset_id, version)
);

CREATE TABLE IF NOT EXISTS memory_agents (
    agent_key   TEXT    NOT NULL,
    wiki_id     TEXT    NOT NULL DEFAULT 'default',
    name        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (wiki_id, agent_key)
);

CREATE TABLE IF NOT EXISTS memory_asset_bindings (
    wiki_id     TEXT    NOT NULL DEFAULT 'default',
    agent_key   TEXT    NOT NULL,
    asset_id    TEXT    NOT NULL,
    mode        TEXT    NOT NULL DEFAULT 'always'
                CHECK (mode IN ('always', 'on_demand')),
    priority    INTEGER NOT NULL DEFAULT 100,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (wiki_id, agent_key, asset_id)
);

CREATE INDEX IF NOT EXISTS idx_memory_bindings_agent
    ON memory_asset_bindings(wiki_id, agent_key, priority);
"""
