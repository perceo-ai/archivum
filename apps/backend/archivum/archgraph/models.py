from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ExtractionMethod(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class CodeNode:
    id: str
    label: str
    kind: str            # symbol|module|type|package|file
    source_file: str
    source_location: str  # "L42" or "L42-L88"


@dataclass(frozen=True)
class CodeEdge:
    source: str
    target: str
    relation: str        # calls|imports|inherits|depends_on|references
    method: ExtractionMethod
    source_file: str
    source_location: str
    confidence: float = 1.0


@dataclass(frozen=True)
class Extraction:
    nodes: list[CodeNode]
    edges: list[CodeEdge]
    error: str | None = None
