from __future__ import annotations

import re
from pathlib import Path


def _make_id(*parts: str) -> str:
    """Lower-case; every run of non-alphanumeric chars -> single '_'; join parts with '_'."""
    slugged = []
    for part in parts:
        s = part.lower()
        s = re.sub(r"[^a-z0-9]+", "_", s)
        s = s.strip("_")
        slugged.append(s)
    return "_".join(slugged)


def _file_stem(path: Path) -> str:
    """Return the file's stem (name without extension)."""
    return path.stem


def _read_text(node, source: bytes) -> str:
    """Return UTF-8 decoded text for the given tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _source_location(node) -> str:
    """Return 'L{start}-L{end}' for the given tree-sitter node (1-indexed)."""
    return f"L{node.start_point[0] + 1}-L{node.end_point[0] + 1}"
