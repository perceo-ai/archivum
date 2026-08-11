from __future__ import annotations

from pathlib import Path

from archivum.archgraph.models import Extraction
from archivum.archgraph.registry import _TS_CONFIG, _TSX_CONFIG


def extract_typescript(path: Path) -> Extraction:
    """Extract nodes and edges from a TypeScript or TSX source file."""
    from archivum.archgraph.extract import _extract_generic

    cfg = _TSX_CONFIG if path.suffix == ".tsx" else _TS_CONFIG
    return _extract_generic(path, cfg)
