"""Tests for the L0 content-addressed blob store."""

from __future__ import annotations

import pytest

from archivum.store.blobs import BlobImmutabilityError, BlobStore
from archivum.store.hashing import sha256_bytes


def test_put_returns_content_hash(tmp_path):
    store = BlobStore(tmp_path)
    data = b"evidence bytes"
    h = store.put(data)
    assert h == sha256_bytes(data)


def test_get_roundtrips(tmp_path):
    store = BlobStore(tmp_path)
    data = b"round trip"
    h = store.put(data)
    assert store.get(h) == data


def test_put_is_deduplicated_and_write_once(tmp_path):
    store = BlobStore(tmp_path)
    data = b"same bytes"
    h1 = store.put(data)
    mtime_before = store.path_for(h1).stat().st_mtime_ns
    h2 = store.put(data)
    mtime_after = store.path_for(h1).stat().st_mtime_ns
    assert h1 == h2
    # Second put must NOT rewrite the existing blob.
    assert mtime_before == mtime_after


def test_exists(tmp_path):
    store = BlobStore(tmp_path)
    h = store.put(b"x")
    assert store.exists(h) is True
    assert store.exists("0" * 64) is False


def test_get_missing_raises_keyerror(tmp_path):
    store = BlobStore(tmp_path)
    with pytest.raises(KeyError):
        store.get("0" * 64)


def test_corrupted_blob_with_wrong_bytes_is_rejected(tmp_path):
    store = BlobStore(tmp_path)
    h = store.put(b"correct")
    # Simulate a pre-existing file at the target path with different bytes.
    path = store.path_for(h)
    path.write_bytes(b"tampered")
    with pytest.raises(BlobImmutabilityError):
        store.put(b"correct")
