from __future__ import annotations

import aiosqlite
import pytest

from archivum.archgraph.lexical import (
    _trigrams,
    build_lexical_index,
    score_nodes,
    trigram_candidates,
)


def test_trigrams_calc():
    assert _trigrams("calc") == {"cal", "alc"}


def test_trigrams_short():
    result = _trigrams("ab")
    assert len(result) == 1
    assert "ab" in result


def test_trigrams_single_char():
    result = _trigrams("x")
    assert len(result) == 1
    assert "x" in result


async def test_candidates_superset(tmp_path):
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        nodes = [
            ("retrieve_code", "retrieve_code"),
            ("format_name", "format_name"),
            ("add", "add"),
        ]
        await build_lexical_index(db, nodes)
        candidates = await trigram_candidates(db, "retrieve")
        assert "retrieve_code" in candidates
        assert "add" not in candidates
    finally:
        await db.close()


async def test_idf_ranks_rare_higher(tmp_path):
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        # "add" appears in many nodes; "hypotenuse" only in one
        nodes = [
            ("node_hypot", "hypotenuse calculation function"),
            ("node_add1", "add two numbers function"),
            ("node_add2", "add values together"),
            ("node_add3", "add items to list"),
            ("node_add4", "add element"),
        ]
        await build_lexical_index(db, nodes)
        all_ids = {n[0] for n in nodes}
        scores = await score_nodes(db, "hypotenuse add", all_ids)
        score_map = {nid: s for s, nid in scores}
        # hypotenuse is rare → higher IDF; node_hypot matches hypotenuse + add both
        # but the question is that a node matching only "hypotenuse" (rare) should score
        # higher than a node matching only "add" (common)
        assert score_map["node_hypot"] > score_map["node_add1"]
    finally:
        await db.close()
