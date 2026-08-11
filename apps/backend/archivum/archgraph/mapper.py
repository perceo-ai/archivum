from __future__ import annotations

import re
from dataclasses import dataclass, field

from archivum.archgraph.models import CodeEdge, CodeNode, Extraction


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Provenance:
    chunk_id: str
    span: str               # e.g. "L5-L6" from the node/edge source_location
    extraction_method: str  # ExtractionMethod value string


@dataclass(frozen=True)
class CandidateEntity:
    id: str
    kind: str
    name: str
    scope: str
    confidence: float
    extraction_method: str
    provenance: list[Provenance]


@dataclass(frozen=True)
class CandidateArtifact:
    id: str
    kind: str
    name: str
    scope: str
    confidence: float
    extraction_method: str
    provenance: list[Provenance]


@dataclass(frozen=True)
class CandidateRelationship:
    id: str
    src_id: str
    dst_id: str
    rel_type: str
    scope: str
    confidence: float
    extraction_method: str
    provenance: list[Provenance]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_ARTIFACT_KINDS: frozenset[str] = frozenset({"file", "repo", "commit", "pr", "test", "deployment"})


def _slug(text: str) -> str:
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    return s.strip("_")


def _rel_id(src: str, rel: str, dst: str) -> str:
    return f"{_slug(src)}__{_slug(rel)}__{_slug(dst)}"


# ---------------------------------------------------------------------------
# Main mapper
# ---------------------------------------------------------------------------

def map_extraction(
    ext: Extraction,
    *,
    scope: str,
    chunk_id: str,
) -> list[object]:
    """Return a flat list of CandidateEntity | CandidateArtifact | CandidateRelationship."""
    results: list[object] = []

    for node in ext.nodes:
        prov = [Provenance(chunk_id=chunk_id, span=node.source_location, extraction_method="EXTRACTED")]
        if node.kind in _ARTIFACT_KINDS:
            results.append(
                CandidateArtifact(
                    id=node.id,
                    kind=node.kind,
                    name=node.label,
                    scope=scope,
                    confidence=1.0,
                    extraction_method="EXTRACTED",
                    provenance=prov,
                )
            )
        else:
            results.append(
                CandidateEntity(
                    id=node.id,
                    kind=node.kind,
                    name=node.label,
                    scope=scope,
                    confidence=1.0,
                    extraction_method="EXTRACTED",
                    provenance=prov,
                )
            )

    for edge in ext.edges:
        method_str = edge.method.value
        prov = [Provenance(chunk_id=chunk_id, span=edge.source_location, extraction_method=method_str)]
        results.append(
            CandidateRelationship(
                id=_rel_id(edge.source, edge.relation, edge.target),
                src_id=edge.source,
                dst_id=edge.target,
                rel_type=edge.relation,
                scope=scope,
                confidence=edge.confidence,
                extraction_method=method_str,
                provenance=prov,
            )
        )

    return results
