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
    -- Version lineage is per-origin (see latest_version_for_origin); identical
    -- bytes ingested from two different origins are distinct sources, each at
    -- its own version 1. Uniqueness is therefore scoped to (origin_uri, version).
    UNIQUE(origin_uri, version)
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

CREATE TABLE IF NOT EXISTS knowledge_objects (
    id                TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,
    label             TEXT NOT NULL,
    scope             TEXT NOT NULL,
    confidence        REAL NOT NULL,
    extraction_method TEXT NOT NULL,
    properties        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_objects_kind_scope
    ON knowledge_objects(kind, scope);

CREATE TABLE IF NOT EXISTS knowledge_relationships (
    id                TEXT PRIMARY KEY,
    src_id            TEXT NOT NULL,
    dst_id            TEXT NOT NULL,
    rel_type          TEXT NOT NULL,
    scope             TEXT NOT NULL,
    confidence        REAL NOT NULL,
    extraction_method TEXT NOT NULL,
    properties        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_knowledge_relationships_src_scope
    ON knowledge_relationships(src_id, scope);
CREATE INDEX IF NOT EXISTS idx_knowledge_relationships_dst_scope
    ON knowledge_relationships(dst_id, scope);

CREATE TABLE IF NOT EXISTS knowledge_citations (
    knowledge_id   TEXT NOT NULL,
    knowledge_type TEXT NOT NULL CHECK (knowledge_type IN ('object', 'relationship')),
    position       INTEGER NOT NULL,
    source_id      TEXT NOT NULL,
    chunk_id       TEXT NOT NULL,
    span_start     INTEGER,
    span_end       INTEGER,
    quote          TEXT,
    PRIMARY KEY (knowledge_type, knowledge_id, position)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_citations_knowledge
    ON knowledge_citations(knowledge_type, knowledge_id, position);
"""
