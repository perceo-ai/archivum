"""Normalization: adapt existing parsers into a NormalizedDoc (text + mime)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from archivum.ingest.parsers import parse_source

_TYPE_TO_MIME: dict[str, str] = {
    "md": "text/markdown",
    "txt": "text/plain",
    "text": "text/plain",
    "rst": "text/x-rst",
    "pdf": "application/pdf",
    "html": "text/html",
    "url": "text/html",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
    "json": "application/json",
    "jsonl": "application/jsonl",
    "epub": "application/epub+zip",
    "code": "text/x-code",
    "eml": "message/rfc822",
    "mbox": "application/mbox",
    "image": "image/*",
    "audio": "audio/*",
    "video": "video/*",
}


@dataclass(frozen=True, slots=True)
class NormalizedDoc:
    text: str
    mime: str
    metadata: dict[str, Any]


async def normalize(origin_uri: str) -> NormalizedDoc:
    """Parse `origin_uri` into normalized text and a mime type."""
    parsed = await parse_source(origin_uri)
    doc_type = str(parsed.metadata.get("type", "")).lower()
    mime = _TYPE_TO_MIME.get(doc_type, "text/plain")
    return NormalizedDoc(text=parsed.text, mime=mime, metadata=dict(parsed.metadata))
