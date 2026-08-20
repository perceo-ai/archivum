"""L1 evidence-lineage models: Source → Document → Chunk (spec §4)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import Enum

from archivum.store.source_types import SourceType


def new_id() -> str:
    """Stable opaque id for L1 objects."""
    return uuid.uuid4().hex


class ExtractionMethod(str, Enum):
    EXTRACTED = "EXTRACTED"
    INFERRED = "INFERRED"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True, slots=True)
class Source:
    id: str
    content_hash: str
    version: int
    source_type: SourceType
    origin_uri: str
    scope: str
    ingested_at: str
    recorded_at: str
    valid_from: str
    valid_to: str | None
    # The vault this evidence belongs to. `scope` is the user's own
    # classification of a source (personal, work); this is the tenancy
    # boundary. Last and defaulted so existing positional construction and rows
    # from a database written before the column existed both still work.
    wiki_id: str = "default"


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    source_id: str
    mime: str
    normalized_hash: str


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    document_id: str
    seq: int
    start_offset: int
    end_offset: int
    text_hash: str


@dataclass(frozen=True, slots=True)
class IngestResult:
    source: Source
    document: Document
    chunks: list[Chunk]
    deduplicated: bool
