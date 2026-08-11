from __future__ import annotations

from pathlib import Path

from archivum.archgraph.extract import extract_file
from archivum.archgraph.extractors.base import _make_id
from archivum.archgraph.models import ExtractionMethod

FIXTURES = Path(__file__).parent / "fixtures" / "ts_sample"
USER_TS = FIXTURES / "user.ts"
WIDGET_TSX = FIXTURES / "widget.tsx"

# Target id for "formatName" imported from "./format":
# module stem = Path("./format").stem = "format"
# symbol = "formatName"
_FORMAT_NAME_ID = _make_id("format", "formatName")


def test_extracts_class_interface() -> None:
    result = extract_file(USER_TS)

    assert result.error is None

    type_nodes = [n for n in result.nodes if n.kind == "type"]
    type_labels = {n.label for n in type_nodes}
    assert "User" in type_labels, f"Expected 'User' in type nodes, got {type_labels}"
    assert "Account" in type_labels, f"Expected 'Account' in type nodes, got {type_labels}"

    symbol_nodes = [n for n in result.nodes if n.kind == "symbol"]
    symbol_labels = {n.label for n in symbol_nodes}
    assert "label" in symbol_labels, f"Expected 'label' in symbol nodes, got {symbol_labels}"


def test_extracts_named_import_edge() -> None:
    result = extract_file(USER_TS)

    assert result.error is None

    import_edges = [e for e in result.edges if e.relation == "imports"]
    assert len(import_edges) >= 1, "Expected at least one imports edge"

    target_ids = {e.target for e in import_edges}
    assert _FORMAT_NAME_ID in target_ids, (
        f"Expected imports edge to {_FORMAT_NAME_ID!r} ({_make_id.__module__}._make_id('format','formatName')), "
        f"got targets: {target_ids}"
    )

    matching = [e for e in import_edges if e.target == _FORMAT_NAME_ID]
    assert matching[0].method == ExtractionMethod.EXTRACTED


def test_tsx_parses_and_extracts_call() -> None:
    result = extract_file(WIDGET_TSX)

    assert result.error is None, f"Expected no error, got: {result.error}"

    call_edges = [e for e in result.edges if e.relation == "calls"]
    assert len(call_edges) >= 1, "Expected at least one calls edge"

    target_ids = {e.target for e in call_edges}
    assert _FORMAT_NAME_ID in target_ids, (
        f"Expected calls edge to {_FORMAT_NAME_ID!r}, got targets: {target_ids}"
    )

    matching = [e for e in call_edges if e.target == _FORMAT_NAME_ID]
    assert matching[0].method == ExtractionMethod.EXTRACTED
    assert matching[0].relation == "calls"
