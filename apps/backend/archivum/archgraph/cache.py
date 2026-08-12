from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

from archivum.archgraph.models import CodeEdge, CodeNode, Extraction, ExtractionMethod

EXTRACTOR_VERSION: str = "v2"


def content_hash(path: Path) -> str:
    """Return sha256 hexdigest of file bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cache_path(path: Path, cache_dir: Path, *, namespace: str | None = None) -> Path:
    """Compute cache entry path using current EXTRACTOR_VERSION."""
    import archivum.archgraph.cache as _self

    hasher = hashlib.sha256()
    hasher.update(path.read_bytes())
    if namespace is not None:
        hasher.update(b"\0")
        hasher.update(namespace.encode("utf-8"))
    h = hasher.hexdigest()
    return cache_dir / "ast" / _self.EXTRACTOR_VERSION / f"{h}.json"


def load_cached(path: Path, cache_dir: Path, *, namespace: str | None = None) -> Extraction | None:
    """Return cached Extraction if available, else None."""
    entry = _cache_path(path, cache_dir, namespace=namespace)
    if not entry.exists():
        return None
    data = json.loads(entry.read_text())
    nodes = [
        CodeNode(
            id=n["id"],
            label=n["label"],
            kind=n["kind"],
            source_file=n["source_file"],
            source_location=n["source_location"],
        )
        for n in data["nodes"]
    ]
    edges = [
        CodeEdge(
            source=e["source"],
            target=e["target"],
            relation=e["relation"],
            method=ExtractionMethod(e["method"]),
            source_file=e["source_file"],
            source_location=e["source_location"],
            confidence=e.get("confidence", 1.0),
        )
        for e in data["edges"]
    ]
    return Extraction(nodes=nodes, edges=edges, error=data.get("error"))


def save_cached(
    path: Path,
    ext: Extraction,
    cache_dir: Path,
    *,
    namespace: str | None = None,
) -> None:
    """Serialize Extraction to cache atomically."""
    entry = _cache_path(path, cache_dir, namespace=namespace)
    entry.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "kind": n.kind,
                "source_file": n.source_file,
                "source_location": n.source_location,
            }
            for n in ext.nodes
        ],
        "edges": [
            {
                "source": e.source,
                "target": e.target,
                "relation": e.relation,
                "method": e.method.value,
                "source_file": e.source_file,
                "source_location": e.source_location,
                "confidence": e.confidence,
            }
            for e in ext.edges
        ],
        "error": ext.error,
    }
    # Atomic write: temp file in same dir, then replace
    fd, tmp = tempfile.mkstemp(dir=entry.parent)
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, entry)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
