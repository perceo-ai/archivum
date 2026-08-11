from __future__ import annotations

from pathlib import Path

import pytest

from archivum.archgraph.extract import extract_file
from archivum.archgraph.extractors.base import _make_id
from archivum.archgraph.models import ExtractionMethod

CALC = Path(__file__).parent / "fixtures" / "py_sample" / "calc.py"


def test_extracts_class_and_methods() -> None:
    result = extract_file(CALC)

    assert result.error is None
    kinds = {n.kind for n in result.nodes}
    assert "file" in kinds
    assert "type" in kinds
    assert "symbol" in kinds

    file_nodes = [n for n in result.nodes if n.kind == "file"]
    assert len(file_nodes) == 1

    type_nodes = [n for n in result.nodes if n.kind == "type"]
    assert any(n.label == "Calculator" for n in type_nodes)

    symbol_nodes = [n for n in result.nodes if n.kind == "symbol"]
    symbol_labels = {n.label for n in symbol_nodes}
    assert "add" in symbol_labels
    assert "hypot" in symbol_labels

    # verify ids via _make_id
    calc_type_id = _make_id("calc", "Calculator")
    add_id = _make_id("calc", "Calculator", "add")
    hypot_id = _make_id("calc", "Calculator", "hypot")
    node_ids = {n.id for n in result.nodes}
    assert calc_type_id in node_ids
    assert add_id in node_ids
    assert hypot_id in node_ids


def test_extracts_import_edge() -> None:
    result = extract_file(CALC)

    assert result.error is None
    import_edges = [e for e in result.edges if e.relation == "imports"]
    assert len(import_edges) >= 1

    math_target = _make_id("math")
    math_edges = [e for e in import_edges if e.target == math_target]
    assert len(math_edges) == 1
    assert math_edges[0].method == ExtractionMethod.EXTRACTED


def test_extracts_intrafile_call() -> None:
    result = extract_file(CALC)

    assert result.error is None
    call_edges = [e for e in result.edges if e.relation == "calls"]

    hypot_id = _make_id("calc", "Calculator", "hypot")
    add_id = _make_id("calc", "Calculator", "add")
    math_sqrt_id = _make_id("math", "sqrt")

    # hypot calls self.add -> intra-file resolution
    intrafile_edge = [e for e in call_edges if e.source == hypot_id and e.target == add_id]
    assert len(intrafile_edge) == 1
    assert intrafile_edge[0].method == ExtractionMethod.EXTRACTED

    # hypot calls math.sqrt -> external reference
    extern_edge = [e for e in call_edges if e.source == hypot_id and e.target == math_sqrt_id]
    assert len(extern_edge) == 1
    assert extern_edge[0].method == ExtractionMethod.EXTRACTED


def test_malformed_file_returns_error(tmp_path: Path) -> None:
    missing = tmp_path / "nonexistent.py"
    result = extract_file(missing)

    assert result.error is not None
    assert result.nodes == []
    assert result.edges == []
