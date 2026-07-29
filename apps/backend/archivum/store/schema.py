"""L1 evidence-lineage SQLite schema (spec §4). Applied idempotently at init."""

from __future__ import annotations

EVIDENCE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            TEXT    PRIMARY KEY,
    content_hash  TEXT    NOT NULL,
    version       INTEGER NOT NULL,
    source_type   TEXT    NOT NULL,
    origin_uri    TEXT    NOT NULL,
    scope         TEXT    NOT NULL DEFAULT 'personal',
    ingested_at   TEXT    NOT NULL,
    recorded_at   TEXT    NOT NULL,
    valid_from    TEXT    NOT NULL,
    valid_to      TEXT,
    UNIQUE(content_hash, version)
);

CREATE INDEX IF NOT EXISTS idx_sources_content_hash ON sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_sources_origin_uri ON sources(origin_uri);
CREATE INDEX IF NOT EXISTS idx_sources_scope ON sources(scope);

CREATE TABLE IF NOT EXISTS documents (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    mime            TEXT NOT NULL,
    normalized_hash TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);

CREATE TABLE IF NOT EXISTS chunks (
    id           TEXT    PRIMARY KEY,
    document_id  TEXT    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset   INTEGER NOT NULL,
    text_hash    TEXT    NOT NULL,
    UNIQUE(document_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks(text_hash);
"""
