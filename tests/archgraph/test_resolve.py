from __future__ import annotations

from archivum.archgraph.models import (
    CodeEdge,
    CodeNode,
    Extraction,
    ExtractionMethod,
)
from archivum.archgraph.resolve import resolve_cross_file


def _node(id: str, label: str, source_file: str) -> CodeNode:
    return CodeNode(id=id, label=label, kind="symbol", source_file=source_file, source_location="L1")


def _edge(source: str, target: str, relation: str, method: ExtractionMethod, source_file: str) -> CodeEdge:
    return CodeEdge(
        source=source,
        target=target,
        relation=relation,
        method=method,
        source_file=source_file,
        source_location="L2",
    )


def test_resolves_imported_call_inferred():
    """Unresolved call from a to b resolves to INFERRED edge when b has exactly one match.

    The edge in file a references a bare name 'helper' via the unresolved target id
    'unknown_helper' (not present in any node set). File b has a node whose id is
    'b_helper' and whose bare name is also 'helper'. The resolver must emit a new
    INFERRED edge from a_run to b_helper.
    """
    node_a = _node("a_run", "run", "a.py")
    # 'unknown_helper' is not a node id in any extraction -> truly unresolved
    edge_a = _edge("a_run", "unknown_helper", "calls", ExtractionMethod.EXTRACTED, "a.py")
    ext_a = Extraction(nodes=[node_a], edges=[edge_a])

    # file b: node b_helper — bare name 'helper' matches 'unknown_helper' bare name
    node_b = _node("b_helper", "helper", "b.py")
    ext_b = Extraction(nodes=[node_b], edges=[])

    new_edges = resolve_cross_file([ext_a, ext_b])
    assert len(new_edges) == 1
    e = new_edges[0]
    assert e.source == "a_run"
    assert e.target == "b_helper"
    assert e.relation == "calls"
    assert e.method == ExtractionMethod.INFERRED


def test_ambiguous_on_collision():
    """When two files each define a symbol with the same bare name, emit AMBIGUOUS edge(s)."""
    node_a = _node("a_run", "run", "a.py")
    # target bare name "helper" -> will match b_helper and c_helper
    edge_a = _edge("a_run", "x_helper", "calls", ExtractionMethod.EXTRACTED, "a.py")
    ext_a = Extraction(nodes=[node_a], edges=[edge_a])

    node_b = _node("b_helper", "helper", "b.py")
    ext_b = Extraction(nodes=[node_b], edges=[])

    node_c = _node("c_helper", "helper", "c.py")
    ext_c = Extraction(nodes=[node_c], edges=[])

    new_edges = resolve_cross_file([ext_a, ext_b, ext_c])
    assert len(new_edges) >= 1
    for e in new_edges:
        assert e.method == ExtractionMethod.AMBIGUOUS


def test_no_duplicate_of_extracted():
    """An edge whose target already exists in the combined node set is not re-emitted."""
    node_a = _node("a_run", "run", "a.py")
    node_b = _node("b_helper", "helper", "b.py")
    # This edge's target b_helper IS in the combined node set (via ext_b) -> not unresolved
    edge_a = _edge("a_run", "b_helper", "calls", ExtractionMethod.EXTRACTED, "a.py")
    ext_a = Extraction(nodes=[node_a], edges=[edge_a])
    ext_b = Extraction(nodes=[node_b], edges=[])

    new_edges = resolve_cross_file([ext_a, ext_b])
    # b_helper is already a known node -> target is resolved, not an unresolved external
    assert new_edges == []
