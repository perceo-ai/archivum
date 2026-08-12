from __future__ import annotations

import json
from pathlib import Path

import pytest

from archivum.archgraph.mapper import (
    CandidateArtifact,
    CandidateEntity,
    CandidateRelationship,
    Provenance,
)
from archivum.db import sqlite as app_sqlite


# ---------------------------------------------------------------------------
# Helpers — hand-built candidates for unit tests
# ---------------------------------------------------------------------------

def _make_entity(id: str, name: str, kind: str = "function", scope: str = "repo:test") -> CandidateEntity:
    prov = [Provenance(chunk_id=f"chunk:{id}", span="L1", extraction_method="EXTRACTED")]
    return CandidateEntity(
        id=id,
        kind=kind,
        name=name,
        scope=scope,
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=prov,
    )


def _make_relationship(
    src: str,
    dst: str,
    rel_type: str = "calls",
    extraction_method: str = "EXTRACTED",
) -> CandidateRelationship:
    prov = [Provenance(chunk_id=f"chunk:{src}", span="L1", extraction_method=extraction_method)]
    rel_id = f"{src}__{rel_type}__{dst}"
    return CandidateRelationship(
        id=rel_id,
        src_id=src,
        dst_id=dst,
        rel_type=rel_type,
        scope="repo:test",
        confidence=0.9,
        extraction_method=extraction_method,
        provenance=prov,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_graph_dict_shapes():
    """build_graph_dict returns nodes with required keys and edges with required keys."""
    from archivum.archgraph.export import build_graph_dict

    e1 = _make_entity("func_add", "add")
    e2 = _make_entity("func_hypot", "hypot")
    rel = _make_relationship("func_hypot", "func_add", "calls")

    g = build_graph_dict([e1, e2, rel])

    assert "nodes" in g
    assert "edges" in g

    node_ids = [n["id"] for n in g["nodes"]]
    # Deterministic: nodes sorted by id
    assert node_ids == sorted(node_ids), "Nodes must be sorted by id"

    for node in g["nodes"]:
        assert "id" in node
        assert "label" in node
        assert "kind" in node
        assert "extraction_method" in node

    edge_found = False
    for edge in g["edges"]:
        assert "source" in edge
        assert "target" in edge
        assert "relation" in edge
        assert "extraction_method" in edge
        if edge["source"] == "func_hypot" and edge["target"] == "func_add":
            edge_found = True
    assert edge_found, "Expected edge from func_hypot to func_add"


def test_export_writes_files(tmp_path):
    """export_graph writes graph.json and graph.html; both are valid and non-empty."""
    from archivum.archgraph.export import export_graph

    e1 = _make_entity("func_add", "add")
    e2 = _make_entity("func_hypot", "hypot")
    rel = _make_relationship("func_hypot", "func_add", "calls")

    json_path, html_path = export_graph([e1, e2, rel], tmp_path)

    assert json_path.exists()
    assert html_path.exists()

    # graph.json must be valid JSON with nodes/edges keys
    data = json.loads(json_path.read_text())
    assert "nodes" in data
    assert "edges" in data

    # graph.html must mention vis-network and embed graph data
    html = html_path.read_text()
    assert html, "graph.html must not be empty"
    assert "vis-network" in html
    assert "nodes" in html  # the embedded graph JS object


def test_export_html_marks_extraction_method(tmp_path):
    """An INFERRED edge in candidates causes HTML to contain a distinguishing marker."""
    from archivum.archgraph.export import export_graph

    e1 = _make_entity("func_a", "a")
    e2 = _make_entity("func_b", "b")
    rel_inferred = _make_relationship("func_a", "func_b", "calls", extraction_method="INFERRED")

    _, html_path = export_graph([e1, e2, rel_inferred], tmp_path)
    html = html_path.read_text()

    # The HTML must distinguish INFERRED edges — either by string or dashes:true
    has_inferred_marker = "INFERRED" in html or "dashes" in html
    assert has_inferred_marker, (
        "Expected HTML to mark INFERRED edges (contain 'INFERRED' or 'dashes')"
    )


def test_cli_export_smoke(git_repo, tmp_path, monkeypatch):
    """CLI with --export writes graph.json to the export directory."""
    from archivum.archgraph.hook import main

    cache_dir = tmp_path / "c"
    export_dir = tmp_path / "g"
    monkeypatch.setattr(app_sqlite, "_db_path", tmp_path / "archivum.db")

    rc = main([
        "ingest", str(git_repo),
        "--scope", "repo:test",
        "--cache-dir", str(cache_dir),
        "--export", str(export_dir),
    ])

    assert rc == 0
    assert (export_dir / "graph.json").exists()
