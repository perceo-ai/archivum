from __future__ import annotations

import pytest

from archivum.archgraph.models import CodeEdge, CodeNode, Extraction, ExtractionMethod
from archivum.archgraph.mapper import (
    CandidateArtifact,
    CandidateEntity,
    CandidateRelationship,
    map_extraction,
)

SCOPE = "repo:archivum"
CHUNK = "chunk-abc"


def _symbol_node() -> CodeNode:
    return CodeNode(
        id="my_module__add",
        label="add",
        kind="symbol",
        source_file="my_module.py",
        source_location="L5-L6",
    )


def _file_node() -> CodeNode:
    return CodeNode(
        id="my_module_py",
        label="my_module.py",
        kind="file",
        source_file="my_module.py",
        source_location="L1-L10",
    )


def _calls_edge() -> CodeEdge:
    return CodeEdge(
        source="my_module__main",
        target="my_module__add",
        relation="calls",
        method=ExtractionMethod.INFERRED,
        source_file="my_module.py",
        source_location="L8-L8",
        confidence=0.9,
    )


def test_maps_symbol_to_entity() -> None:
    node = _symbol_node()
    ext = Extraction(nodes=[node], edges=[])

    result = map_extraction(ext, scope=SCOPE, chunk_id=CHUNK)

    entities = [c for c in result if isinstance(c, CandidateEntity)]
    assert len(entities) == 1
    e = entities[0]
    assert e.kind == "symbol"
    assert e.name == "add"
    assert e.id == "my_module__add"
    assert e.scope == SCOPE
    assert e.confidence == 1.0
    assert e.extraction_method == "EXTRACTED"
    assert len(e.provenance) == 1
    prov = e.provenance[0]
    assert prov.chunk_id == CHUNK
    assert prov.span == "L5-L6"
    assert prov.extraction_method == "EXTRACTED"


def test_maps_file_to_artifact() -> None:
    node = _file_node()
    ext = Extraction(nodes=[node], edges=[])

    result = map_extraction(ext, scope=SCOPE, chunk_id=CHUNK)

    artifacts = [c for c in result if isinstance(c, CandidateArtifact)]
    assert len(artifacts) == 1
    a = artifacts[0]
    assert a.kind == "file"
    assert a.name == "my_module.py"
    assert a.scope == SCOPE


def test_maps_edge_to_relationship_preserves_method() -> None:
    edge = _calls_edge()
    ext = Extraction(nodes=[], edges=[edge])

    result = map_extraction(ext, scope=SCOPE, chunk_id=CHUNK)

    rels = [c for c in result if isinstance(c, CandidateRelationship)]
    assert len(rels) == 1
    r = rels[0]
    assert r.rel_type == "calls"
    assert r.extraction_method == "INFERRED"
    assert r.src_id == "my_module__main"
    assert r.dst_id == "my_module__add"
    assert r.confidence == 0.9
    assert len(r.provenance) == 1
    assert r.provenance[0].extraction_method == "INFERRED"
    assert r.provenance[0].span == "L8-L8"
    assert r.provenance[0].chunk_id == CHUNK


def test_validation_rejects_no_provenance(fake_validation) -> None:
    node = _symbol_node()
    ext = Extraction(nodes=[node], edges=[])
    candidates = map_extraction(ext, scope=SCOPE, chunk_id=CHUNK)

    bad = CandidateEntity(
        id="bad",
        kind="symbol",
        name="bad",
        scope=SCOPE,
        confidence=1.0,
        extraction_method="EXTRACTED",
        provenance=[],
    )
    good = candidates[0]  # real mapped entity has non-empty provenance

    fake_validation.validate_batch([bad, good])

    assert bad in fake_validation.rejected
    assert good in fake_validation.accepted
    assert bad not in fake_validation.accepted
    assert good not in fake_validation.rejected
