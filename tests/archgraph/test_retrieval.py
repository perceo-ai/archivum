from __future__ import annotations

import aiosqlite
import pytest

from archivum.archgraph.lexical import build_lexical_index
from archivum.archgraph.retrieval import ScopedSubgraph, retrieve_code

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_node(
    node_id: str,
    *,
    scope: str = "repo:a",
    kind: str = "function",
    extraction_method: str = "EXTRACTED",
    citation: str = "",
) -> dict:
    return {
        "label": node_id,
        "kind": kind,
        "scope": scope,
        "confidence": 1.0,
        "extraction_method": extraction_method,
        "citation": citation or node_id,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_seeds_from_lexical(tmp_path):
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        nodes = [
            ("hypot", "hypot hypotenuse function"),
            ("add", "add numbers"),
        ]
        await build_lexical_index(db, nodes)

        adjacency = {"hypot": [], "add": []}
        node_meta = {
            "hypot": _make_node("hypot"),
            "add": _make_node("add"),
        }

        result = await retrieve_code(
            db, "hypot", adjacency=adjacency, node_meta=node_meta
        )

        assert isinstance(result, ScopedSubgraph)
        node_ids = {n["id"] for n in result.nodes}
        assert "hypot" in node_ids
    finally:
        await db.close()


async def test_bfs_expands_neighbors(tmp_path):
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        nodes = [
            ("hypot", "hypot hypotenuse function"),
            ("add", "add numbers"),
        ]
        await build_lexical_index(db, nodes)

        adjacency = {
            "hypot": [
                {
                    "target": "add",
                    "relation": "calls",
                    "extraction_method": "EXTRACTED",
                    "confidence": 1.0,
                }
            ],
            "add": [],
        }
        node_meta = {
            "hypot": _make_node("hypot"),
            "add": _make_node("add"),
        }

        result = await retrieve_code(
            db, "hypot", adjacency=adjacency, node_meta=node_meta, depth=2
        )

        node_ids = {n["id"] for n in result.nodes}
        assert "hypot" in node_ids
        assert "add" in node_ids
    finally:
        await db.close()


async def test_respects_max_nodes_and_scope(tmp_path):
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        nodes = [
            ("hypot", "hypot hypotenuse function"),
            ("add", "add numbers"),
            ("other", "other repo function"),
        ]
        await build_lexical_index(db, nodes)

        adjacency = {
            "hypot": [
                {
                    "target": "add",
                    "relation": "calls",
                    "extraction_method": "EXTRACTED",
                    "confidence": 1.0,
                },
                {
                    "target": "other",
                    "relation": "calls",
                    "extraction_method": "EXTRACTED",
                    "confidence": 1.0,
                },
            ],
            "add": [],
            "other": [],
        }
        node_meta = {
            "hypot": _make_node("hypot", scope="repo:a"),
            "add": _make_node("add", scope="repo:a"),
            "other": _make_node("other", scope="repo:b"),
        }

        # max_nodes=1 → at most 1 node
        result_max1 = await retrieve_code(
            db, "hypot", adjacency=adjacency, node_meta=node_meta, max_nodes=1
        )
        assert len(result_max1.nodes) <= 1

        # scope="repo:a" → excludes repo:b node
        result_scope = await retrieve_code(
            db,
            "hypot",
            adjacency=adjacency,
            node_meta=node_meta,
            scope="repo:a",
            depth=2,
        )
        node_ids = {n["id"] for n in result_scope.nodes}
        assert "other" not in node_ids
    finally:
        await db.close()


async def test_nodes_carry_method_and_citation(tmp_path):
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        nodes = [
            ("hypot", "hypot hypotenuse function"),
            ("add", "add numbers"),
        ]
        await build_lexical_index(db, nodes)

        adjacency = {
            "hypot": [
                {
                    "target": "add",
                    "relation": "calls",
                    "extraction_method": "EXTRACTED",
                    "confidence": 1.0,
                }
            ],
            "add": [],
        }
        node_meta = {
            "hypot": _make_node("hypot", extraction_method="EXTRACTED", citation="file.py:10"),
            "add": _make_node("add", extraction_method="INFERRED", citation=""),
        }

        result = await retrieve_code(
            db, "hypot", adjacency=adjacency, node_meta=node_meta, depth=2
        )

        for node in result.nodes:
            assert "extraction_method" in node and node["extraction_method"]
            assert "citation" in node and node["citation"]
    finally:
        await db.close()
