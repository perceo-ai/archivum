"""Content-addressing primitives — sha256 over raw bytes."""

from __future__ import annotations

import hashlib


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex sha256 digest of raw bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str, *, encoding: str = "utf-8") -> str:
    """Return the sha256 digest of text encoded with `encoding` (default utf-8)."""
    return sha256_bytes(text.encode(encoding))
