from __future__ import annotations

import archivum.archgraph.cache as cache_mod
from archivum.archgraph.cache import content_hash, load_cached, save_cached
from archivum.archgraph.models import (
    CodeEdge,
    CodeNode,
    Extraction,
    ExtractionMethod,
)


def _make_extraction() -> Extraction:
    node = CodeNode(
        id="a_run",
        label="run",
        kind="symbol",
        source_file="a.py",
        source_location="L1",
    )
    edge = CodeEdge(
        source="a_run",
        target="b_helper",
        relation="calls",
        method=ExtractionMethod.INFERRED,
        source_file="a.py",
        source_location="L2",
    )
    return Extraction(nodes=[node], edges=[edge])


def test_roundtrip(tmp_path):
    f = tmp_path / "a.py"
    f.write_bytes(b"def run(): helper()")
    cache_dir = tmp_path / "cache"
    ext = _make_extraction()
    save_cached(f, ext, cache_dir)
    result = load_cached(f, cache_dir)
    assert result is not None
    assert len(result.nodes) == 1
    assert result.nodes[0].id == "a_run"
    assert len(result.edges) == 1
    assert result.edges[0].method == ExtractionMethod.INFERRED
    assert result.error is None


def test_miss_on_changed_content(tmp_path):
    f = tmp_path / "a.py"
    f.write_bytes(b"def run(): helper()")
    cache_dir = tmp_path / "cache"
    ext = _make_extraction()
    save_cached(f, ext, cache_dir)
    # mutate file content -> hash changes
    f.write_bytes(b"def run(): other()")
    assert load_cached(f, cache_dir) is None


def test_version_namespacing(monkeypatch, tmp_path):
    f = tmp_path / "a.py"
    f.write_bytes(b"def run(): helper()")
    cache_dir = tmp_path / "cache"
    ext = _make_extraction()

    monkeypatch.setattr(cache_mod, "EXTRACTOR_VERSION", "v1")
    save_cached(f, ext, cache_dir)

    monkeypatch.setattr(cache_mod, "EXTRACTOR_VERSION", "v2")
    assert load_cached(f, cache_dir) is None
