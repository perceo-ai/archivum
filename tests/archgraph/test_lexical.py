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


async def test_build_index_idempotent_on_duplicate_node_ids(tmp_path):
    # Real repos emit colliding node ids (e.g. every __init__.py file node).
    # The index is a projection keyed by node_id, so a duplicate id must not
    # crash the build — last text wins, one row per id.
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        await build_lexical_index(
            db,
            [("dup", "first version"), ("dup", "second version"), ("other", "x")],
        )
        cur = await db.execute("SELECT COUNT(*) FROM code_node_text")
        assert (await cur.fetchone())[0] == 2  # dup collapsed to one row
        cur = await db.execute("SELECT text FROM code_node_text WHERE node_id='dup'")
        assert (await cur.fetchone())[0] == "second version"  # last wins
    finally:
        await db.close()


async def test_rebuilding_one_scope_leaves_other_scopes_indexed(tmp_path):
    # The projection used to be one global bucket cleared on every rebuild, so
    # indexing the second repository silently erased the first one's rows. Every
    # repo but the most recently indexed then returned no seeds at all.
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        await build_lexical_index(
            db, [("a:retry", "retry handler")], scope="repo:default:a"
        )
        await build_lexical_index(
            db, [("b:parser", "parser entry")], scope="repo:default:b"
        )

        assert await trigram_candidates(
            db, "retry", scope="repo:default:a"
        ) == {"a:retry"}
        assert await trigram_candidates(
            db, "parser", scope="repo:default:b"
        ) == {"b:parser"}
        # A scoped query must not reach into another repository's rows.
        assert await trigram_candidates(db, "parser", scope="repo:default:a") == set()
    finally:
        await db.close()


async def test_rebuilding_a_scope_replaces_only_its_own_rows(tmp_path):
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        await build_lexical_index(
            db, [("a:retry", "retry handler")], scope="repo:default:a"
        )
        await build_lexical_index(
            db, [("b:parser", "parser entry")], scope="repo:default:b"
        )
        # Re-index a with different contents: its old row goes, b's stays.
        await build_lexical_index(
            db, [("a:backoff", "backoff policy")], scope="repo:default:a"
        )

        assert await trigram_candidates(db, "retry", scope="repo:default:a") == set()
        assert await trigram_candidates(
            db, "backoff", scope="repo:default:a"
        ) == {"a:backoff"}
        assert await trigram_candidates(
            db, "parser", scope="repo:default:b"
        ) == {"b:parser"}
    finally:
        await db.close()


async def test_build_index_migrates_a_pre_scope_projection(tmp_path):
    # Deployed vaults have scope-less tables. The projection is derived, so the
    # builder drops and rebuilds rather than inventing a scope for old rows.
    db = await aiosqlite.connect(tmp_path / "idx.db")
    try:
        await db.executescript(
            """
            CREATE TABLE code_trigram (trigram TEXT NOT NULL, node_id TEXT NOT NULL);
            CREATE TABLE code_node_text (
                node_id TEXT PRIMARY KEY, text TEXT NOT NULL
            );
            INSERT INTO code_node_text (node_id, text) VALUES ('old', 'stale row');
            INSERT INTO code_trigram (trigram, node_id) VALUES ('sta', 'old');
            """
        )
        await db.commit()

        await build_lexical_index(
            db, [("a:retry", "retry handler")], scope="repo:default:a"
        )

        cur = await db.execute("SELECT node_id, scope FROM code_node_text")
        assert await cur.fetchall() == [("a:retry", "repo:default:a")]
    finally:
        await db.close()


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
