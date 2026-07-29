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


_SRC_COLS = "id, content_hash, version, source_type, origin_uri, scope, ingested_at, recorded_at, valid_from, valid_to"


def test_sources_unique_origin_version():
    # Version lineage is per-origin: the same (origin_uri, version) pair must be
    # rejected even when the content differs (a changed re-ingest gets a NEW
    # version, never a duplicate version at the same origin).
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    row = ("id1", "a" * 64, 1, "document", "file:///x", "personal", "t", "t", "t", None)
    conn.execute(f"INSERT INTO sources ({_SRC_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)", row)
    dup = ("id2", "b" * 64, 1, "document", "file:///x", "personal", "t", "t", "t", None)
    try:
        conn.execute(f"INSERT INTO sources ({_SRC_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)", dup)
        raise AssertionError("duplicate (origin_uri, version) must be rejected")
    except sqlite3.IntegrityError:
        pass


def test_same_content_from_different_origins_is_allowed():
    # Identical bytes saved at two different origins are distinct sources, each
    # at version 1. The global content_hash must NOT collide across origins.
    conn = sqlite3.connect(":memory:")
    _apply(conn)
    a = ("id1", "h" * 64, 1, "document", "file:///x", "personal", "t", "t", "t", None)
    b = ("id2", "h" * 64, 1, "document", "file:///y", "personal", "t", "t", "t", None)
    conn.execute(f"INSERT INTO sources ({_SRC_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)", a)
    conn.execute(f"INSERT INTO sources ({_SRC_COLS}) VALUES (?,?,?,?,?,?,?,?,?,?)", b)
    count = conn.execute("SELECT COUNT(*) FROM sources WHERE content_hash=?", ("h" * 64,)).fetchone()[0]
    assert count == 2


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
