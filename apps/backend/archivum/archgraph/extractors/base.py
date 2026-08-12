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


def _file_namespace(path: Path, *, root: Path | None = None, scope: str | None = None) -> str:
    """Return a deterministic file namespace for code IDs."""
    if root is None and scope is None:
        return _file_stem(path)

    try:
        rel_path = path.resolve().relative_to(root.resolve()) if root is not None else path.name
    except ValueError:
        rel_path = path.name

    rel_without_suffix = (
        rel_path.with_suffix("")
        if isinstance(rel_path, Path)
        else Path(rel_path).with_suffix("")
    )
    parts = [part for part in (scope, rel_without_suffix.as_posix()) if part]
    return _make_id(*parts)


def _read_text(node, source: bytes) -> str:
    """Return UTF-8 decoded text for the given tree-sitter node."""
    return source[node.start_byte:node.end_byte].decode("utf-8", "replace")


def _source_location(node) -> str:
    """Return 'L{start}-L{end}' for the given tree-sitter node (1-indexed)."""
    return f"L{node.start_point[0] + 1}-L{node.end_point[0] + 1}"
