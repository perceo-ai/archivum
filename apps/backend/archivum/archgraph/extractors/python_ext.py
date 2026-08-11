from __future__ import annotations

from pathlib import Path

from archivum.archgraph.models import Extraction
from archivum.archgraph.registry import _PYTHON_CONFIG


def extract_python(path: Path) -> Extraction:
    """Extract nodes and edges from a Python source file."""
    from archivum.archgraph.extract import _extract_generic

    return _extract_generic(path, _PYTHON_CONFIG)
