"""Settings must expose a blob_dir path for the L0 store."""

from __future__ import annotations

from pathlib import Path

from archivum.config import Settings


def test_default_blob_dir():
    assert Settings().blob_dir == Path("/data/blobs")


def test_blob_dir_is_overridable(tmp_path):
    s = Settings(blob_dir=tmp_path / "blobs")
    assert s.blob_dir == tmp_path / "blobs"
