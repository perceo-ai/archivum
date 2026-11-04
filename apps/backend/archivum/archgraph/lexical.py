from __future__ import annotations

# L2 index — SQLite-backed trigram+IDF lexical index for code retrieval.
# NO VECTORS — Global Constraint 3: code retrieval uses graph traversal + lexical
# scoring only. Qdrant/embeddings are reserved for natural-language sources.

import math
import re

import aiosqlite


def _trigrams(text: str) -> set[str]:
    """Return the set of length-3 substrings of lowercased text.

    For strings shorter than 3 characters, returns a single-element set
    containing the whole lowercased string so short identifiers still index.
    """
    t = text.lower()
    if len(t) < 3:
        return {t}
    return {t[i : i + 3] for i in range(len(t) - 2)}


# Every row carries the scope it was projected from. Without it the index is a
# single global bucket, and because a rebuild clears before repopulating,
# indexing one repository silently erased every other repository's rows — the
# surviving repo answered every query and all the others returned no seeds at
# all. Scope is part of the primary key because ids collide across repos (every
# repository has an `__init__.py` file node).
_SCHEMA = """
CREATE TABLE IF NOT EXISTS code_trigram (
    scope   TEXT NOT NULL,
    trigram TEXT NOT NULL,
    node_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS code_node_text (
    scope   TEXT NOT NULL,
    node_id TEXT NOT NULL,
    text    TEXT NOT NULL,
    PRIMARY KEY (scope, node_id)
);
-- `trigram IN (...)` is the hot lookup on every code query and had no index at
-- all, so each retrieval scanned the whole posting list.
CREATE INDEX IF NOT EXISTS idx_code_trigram_scope_trigram
    ON code_trigram(scope, trigram);
CREATE INDEX IF NOT EXISTS idx_code_trigram_trigram
    ON code_trigram(trigram);
CREATE INDEX IF NOT EXISTS idx_code_node_text_scope
    ON code_node_text(scope);
"""


async def _ensure_schema(conn: aiosqlite.Connection) -> None:
    """Create the projection tables, migrating pre-scope ones by discarding them.

    These two tables are a derived projection of the canonical code objects, so
    throwing them away costs an ingest and never loses source data. That is
    cheaper and less error-prone than back-filling a scope we no longer know:
    rows written before this column existed cannot be attributed to a repo.
    """
    for table in ("code_trigram", "code_node_text"):
        cursor = await conn.execute(f"PRAGMA table_info({table})")
        columns = {row[1] for row in await cursor.fetchall()}
        if columns and "scope" not in columns:
            await conn.execute(f"DROP TABLE {table}")
    await conn.executescript(_SCHEMA)


async def build_lexical_index(
    conn: aiosqlite.Connection,
    code_nodes: list[tuple[str, str]],
    *,
    scope: str = "",
) -> None:
    """Build (or rebuild) the trigram posting list and node text tables.

    Only `scope`'s rows are cleared, so rebuilding one repository leaves every
    other repository's index intact.

    Args:
        conn: An open aiosqlite connection.
        code_nodes: List of (node_id, text) pairs.
        scope: The scope these nodes belong to, e.g. `repo:default:archivum`.
    """
    await _ensure_schema(conn)
    await conn.execute("DELETE FROM code_trigram WHERE scope = ?", (scope,))
    await conn.execute("DELETE FROM code_node_text WHERE scope = ?", (scope,))

    # Collapse duplicate node_ids (last text wins). The index is a rebuildable
    # projection keyed by node_id, so the same id is the same node — real repos
    # legitimately emit colliding ids (e.g. every __init__.py's file node). This
    # keeps the build idempotent instead of hitting the PK/duplicate-posting.
    deduped: dict[str, str] = {node_id: text for node_id, text in code_nodes}

    for node_id, text in deduped.items():
        await conn.execute(
            "INSERT INTO code_node_text (scope, node_id, text) VALUES (?, ?, ?)",
            (scope, node_id, text),
        )
        await conn.executemany(
            "INSERT INTO code_trigram (scope, trigram, node_id) VALUES (?, ?, ?)",
            [(scope, tri, node_id) for tri in _trigrams(text)],
        )

    await conn.commit()


async def trigram_candidates(
    conn: aiosqlite.Connection,
    query: str,
    *,
    scope: str | None = None,
) -> set[str]:
    """Return the union of node_ids that share at least one trigram with query.

    `scope` filters in SQL rather than afterwards in Python, so a query against
    one repository does not pay for every other repository's postings.
    """
    tris = _trigrams(query)
    if not tris:
        return set()

    placeholders = ",".join("?" * len(tris))
    sql = f"SELECT DISTINCT node_id FROM code_trigram WHERE trigram IN ({placeholders})"
    params: tuple[object, ...] = tuple(tris)
    if scope is not None:
        sql += " AND scope = ?"
        params += (scope,)
    cursor = await conn.execute(sql, params)
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


def _query_terms(query: str) -> list[str]:
    """Split query into lowercase tokens on whitespace and underscores."""
    return [t for t in re.split(r"[\s_]+", query.lower()) if t]


async def score_nodes(
    conn: aiosqlite.Connection,
    query: str,
    candidate_ids: set[str],
    *,
    scope: str | None = None,
) -> list[tuple[float, str]]:
    """Score candidate nodes using IDF-weighted term matching.

    IDF(term) = ln((N+1)/(df+1)) + 1
    where N = total docs and df = docs whose text contains the term (substring,
    case-insensitive).  A node's score = sum of IDF(term) for each distinct query
    term that appears as a substring in the node's text.

    Returns list of (score, node_id) sorted by score DESC, then node_id ASC.
    """
    if not candidate_ids:
        return []

    # The corpus is the scope being searched, not the whole vault. Scoping it
    # keeps IDF meaningful per repository and keeps the `LIKE` scans below
    # proportional to one repo instead of every repo ever indexed.
    scope_sql = "" if scope is None else " AND scope = ?"
    scope_params: tuple[object, ...] = () if scope is None else (scope,)
    where_scope = "" if scope is None else " WHERE scope = ?"

    # Fetch total doc count
    cursor = await conn.execute(
        f"SELECT COUNT(*) FROM code_node_text{where_scope}", scope_params
    )
    row = await cursor.fetchone()
    n_docs: int = row[0] if row else 0

    terms = list(dict.fromkeys(_query_terms(query)))  # distinct, order-preserved

    # Fetch texts for candidates only
    placeholders = ",".join("?" * len(candidate_ids))
    cursor = await conn.execute(
        f"SELECT node_id, text FROM code_node_text WHERE node_id IN ({placeholders})"
        f"{scope_sql}",
        tuple(candidate_ids) + scope_params,
    )
    node_texts: dict[str, str] = {r[0]: r[1].lower() for r in await cursor.fetchall()}

    # Compute IDF for each term (df = count across all docs in scope, not just
    # the candidates).
    term_idf: dict[str, float] = {}
    for term in terms:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM code_node_text WHERE lower(text) LIKE ?" + scope_sql,
            (f"%{term}%",) + scope_params,
        )
        df_row = await cursor.fetchone()
        df = df_row[0] if df_row else 0
        term_idf[term] = math.log((n_docs + 1) / (df + 1)) + 1.0

    results: list[tuple[float, str]] = []
    for node_id, text in node_texts.items():
        score = sum(
            term_idf[term] for term in terms if term in text
        )
        results.append((score, node_id))

    results.sort(key=lambda x: (-x[0], x[1]))
    return results
