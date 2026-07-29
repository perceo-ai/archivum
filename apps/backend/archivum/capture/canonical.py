"""Deterministic canonical JSON for a Conversation + its content hash (L0 key)."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from archivum.capture.schema import Conversation
from archivum.store.hashing import sha256_bytes


def to_canonical_dict(conv: Conversation) -> dict[str, Any]:
    d = dataclasses.asdict(conv)
    d.pop("metadata", None)  # transport-only, excluded from identity
    return d


def to_canonical_bytes(conv: Conversation) -> bytes:
    return json.dumps(
        to_canonical_dict(conv),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def content_hash(conv: Conversation) -> str:
    return sha256_bytes(to_canonical_bytes(conv))
