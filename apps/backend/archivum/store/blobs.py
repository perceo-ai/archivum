"""L0 immutable evidence: content-addressed, write-once blob store on disk."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from archivum.store.hashing import sha256_bytes


class BlobImmutabilityError(RuntimeError):
    """Raised when an existing blob's bytes do not match the content hash."""


class BlobStore:
    """Write-once content-addressed store. Blobs are keyed by sha256(bytes)."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, content_hash: str) -> Path:
        """Sharded path: root/<h[0:2]>/<h[2:4]>/<hash> to avoid huge dirs."""
        return self.root / content_hash[0:2] / content_hash[2:4] / content_hash

    def exists(self, content_hash: str) -> bool:
        return self.path_for(content_hash).is_file()

    def put(self, data: bytes) -> str:
        """Write `data` once and return its content hash. Idempotent."""
        content_hash = sha256_bytes(data)
        target = self.path_for(content_hash)
        if target.exists():
            # Write-once: verify the existing blob matches; never overwrite.
            if target.read_bytes() != data:
                raise BlobImmutabilityError(
                    f"blob {content_hash} exists with different bytes"
                )
            return content_hash

        target.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: write to a temp file in the same dir, then rename.
        fd, tmp_name = tempfile.mkstemp(dir=str(target.parent))
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_name, target)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise
        return content_hash

    def get(self, content_hash: str) -> bytes:
        target = self.path_for(content_hash)
        if not target.is_file():
            raise KeyError(content_hash)
        return target.read_bytes()
