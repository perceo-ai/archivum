from __future__ import annotations

from archivum.archgraph.models import CodeEdge, CodeNode, Extraction, ExtractionMethod


def test_extraction_method_values():
    assert ExtractionMethod.EXTRACTED.value == "EXTRACTED"
    assert len(ExtractionMethod) == 3


def test_codeedge_defaults():
    node = CodeNode(
        id="foo",
        label="Foo",
        kind="symbol",
        source_file="foo.py",
        source_location="L1",
    )
    edge = CodeEdge(
        source="foo",
        target="bar",
        relation="calls",
        method=ExtractionMethod.EXTRACTED,
        source_file="foo.py",
        source_location="L1",
    )
    # frozen dataclasses are hashable
    assert hash(node) is not None
    assert hash(edge) is not None
    assert edge.confidence == 1.0

    # Extraction constructs fine with list fields; .error defaults to None
    ext = Extraction(nodes=[node], edges=[edge])
    assert ext.error is None
