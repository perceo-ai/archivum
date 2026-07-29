"""Tests that the evidence schema is valid, idempotent SQLite DDL."""

from __future__ import annotations

import sqlite3

from archivum.store.schema import EVIDENCE_SCHEMA


def _apply(conn):
    conn.executescript(EVIDENCE_SCHEMA)


def test_schema_applies_and_is_idempotent():
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    _apply(conn)  # second run must not error (IF NOT EXISTS)
    tables = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"sources", "documents", "chunks"} <= tables


def test_sources_unique_content_hash_version():
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    row = (
        "id1", "h" * 64, 1, "document", "file:///x", "personal",
        "t", "t", "t", None,
    )
    cols = "id, content_hash, version, source_type, origin_uri, scope, ingested_at, recorded_at, valid_from, valid_to"
    conn.execute(f"INSERT INTO sources ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?)", row)
    dup = ("id2", "h" * 64, 1, "document", "file:///x", "personal", "t", "t", "t", None)
    try:
        conn.execute(f"INSERT INTO sources ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?)", dup)
        raise AssertionError("duplicate (content_hash, version) must be rejected")
    except sqlite3.IntegrityError:
        pass


def test_chunks_unique_document_seq():
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    conn.execute(
        "INSERT INTO chunks (id, document_id, seq, start_offset, end_offset, text_hash) "
        "VALUES (?,?,?,?,?,?)",
        ("c1", "d1", 0, 0, 5, "t" * 64),
    )
    try:
        conn.execute(
            "INSERT INTO chunks (id, document_id, seq, start_offset, end_offset, text_hash) "
            "VALUES (?,?,?,?,?,?)",
            ("c2", "d1", 0, 0, 5, "t" * 64),
        )
        raise AssertionError("duplicate (document_id, seq) must be rejected")
    except sqlite3.IntegrityError:
        pass
