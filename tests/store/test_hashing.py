"""Tests for archivum.store.hashing."""

from __future__ import annotations

import hashlib

from archivum.store.hashing import sha256_bytes, sha256_text


def test_sha256_bytes_matches_hashlib():
    data = b"hello archivum"
    assert sha256_bytes(data) == hashlib.sha256(data).hexdigest()


def test_sha256_bytes_is_64_hex_chars():
    digest = sha256_bytes(b"anything")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_sha256_text_equals_bytes_of_utf8():
    assert sha256_text("café") == sha256_bytes("café".encode("utf-8"))


def test_sha256_is_deterministic():
    assert sha256_bytes(b"x") == sha256_bytes(b"x")
