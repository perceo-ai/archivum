from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ExtractionMethod = Literal["EXTRACTED", "INFERRED", "AMBIGUOUS", "USER_AUTHORED"]


class Citation(BaseModel):
    source_id: str
    chunk_id: str
    span_start: int | None
    span_end: int | None
    quote: str | None


class KnowledgeObject(BaseModel):
    id: str
    kind: str
    label: str
    scope: str
    confidence: float
    extraction_method: ExtractionMethod
    citations: list[Citation] = Field(min_length=1)
    properties: dict[str, Any]


class KnowledgeRelationship(BaseModel):
    id: str
    src_id: str
    dst_id: str
    rel_type: str
    scope: str
    confidence: float
    extraction_method: ExtractionMethod
    citations: list[Citation] = Field(min_length=1)
    properties: dict[str, Any]


class ContextNode(BaseModel):
    id: str
    label: str
    node_type: str
    scope: str = "person:self"
    extraction_method: ExtractionMethod = "EXTRACTED"
    confidence: float = 1.0
    citations: list[Citation] = Field(default_factory=list)


class ContextEdge(BaseModel):
    from_id: str
    to_id: str
    relation: str
    scope: str
    extraction_method: ExtractionMethod = "EXTRACTED"
    confidence: float = 1.0
    citations: list[Citation] = Field(min_length=1)


class ContextPackage(BaseModel):
    query: str
    seeds: list[str]
    nodes: list[ContextNode]
    edges: list[ContextEdge]
    citations: list[Citation]
    insufficient_evidence: bool
    reason: str | None
