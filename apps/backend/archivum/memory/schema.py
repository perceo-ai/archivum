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
    approved_by TEXT,
    reviewed_at TEXT,
    supersedes  TEXT    NOT NULL DEFAULT '[]',
    superseded_by TEXT  NOT NULL DEFAULT '[]',
    conflict_lineage TEXT NOT NULL DEFAULT '[]',
    retired_at  TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_memory_assets_wiki_type
    ON memory_assets(wiki_id, asset_type, status);
CREATE INDEX IF NOT EXISTS idx_memory_assets_scope
    ON memory_assets(scope);
CREATE INDEX IF NOT EXISTS idx_memory_assets_layer
    ON memory_assets(wiki_id, layer);

CREATE TABLE IF NOT EXISTS memory_scopes (
    id               TEXT    NOT NULL,
    wiki_id          TEXT    NOT NULL DEFAULT 'default',
    scope_type       TEXT    NOT NULL
                     CHECK (scope_type IN ('human', 'topic', 'project',
                                           'repo', 'person', 'org')),
    name             TEXT    NOT NULL,
    parent_scope_id  TEXT,
    budget_tokens    INTEGER NOT NULL DEFAULT 4000,
    budget_items     INTEGER NOT NULL DEFAULT 20,
    retention_policy TEXT    NOT NULL DEFAULT '{}',
    created_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at       TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (wiki_id, id)
);

CREATE INDEX IF NOT EXISTS idx_memory_scopes_type
    ON memory_scopes(wiki_id, scope_type);

INSERT OR IGNORE INTO memory_scopes
    (id, wiki_id, scope_type, name, budget_tokens, budget_items, retention_policy)
VALUES
    ('person:self', 'default', 'human', 'Self', 4000, 20,
     '{"candidate_ttl_days":30,"archive_raw_after_days":180}');

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
