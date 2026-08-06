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


async def build_lexical_index(
    conn: aiosqlite.Connection,
    code_nodes: list[tuple[str, str]],
) -> None:
    """Build (or rebuild) the trigram posting list and node text tables.

    Tables created if they don't exist; existing rows are cleared before
    repopulating, making the function idempotent/rebuildable.

    Args:
        conn: An open aiosqlite connection.
        code_nodes: List of (node_id, text) pairs.
    """
    await conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS code_trigram (
            trigram TEXT NOT NULL,
            node_id TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS code_node_text (
            node_id TEXT PRIMARY KEY,
            text    TEXT NOT NULL
        );
        DELETE FROM code_trigram;
        DELETE FROM code_node_text;
        """
    )

    # Collapse duplicate node_ids (last text wins). The index is a rebuildable
    # projection keyed by node_id, so the same id is the same node — real repos
    # legitimately emit colliding ids (e.g. every __init__.py's file node). This
    # keeps the build idempotent instead of hitting the PK/duplicate-posting.
    deduped: dict[str, str] = {node_id: text for node_id, text in code_nodes}

    for node_id, text in deduped.items():
        await conn.execute(
            "INSERT INTO code_node_text (node_id, text) VALUES (?, ?)",
            (node_id, text),
        )
        for tri in _trigrams(text):
            await conn.execute(
                "INSERT INTO code_trigram (trigram, node_id) VALUES (?, ?)",
                (tri, node_id),
            )

    await conn.commit()


async def trigram_candidates(
    conn: aiosqlite.Connection,
    query: str,
) -> set[str]:
    """Return the union of node_ids that share at least one trigram with query."""
    tris = _trigrams(query)
    if not tris:
        return set()

    placeholders = ",".join("?" * len(tris))
    cursor = await conn.execute(
        f"SELECT DISTINCT node_id FROM code_trigram WHERE trigram IN ({placeholders})",
        tuple(tris),
    )
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


def _query_terms(query: str) -> list[str]:
    """Split query into lowercase tokens on whitespace and underscores."""
    return [t for t in re.split(r"[\s_]+", query.lower()) if t]


async def score_nodes(
    conn: aiosqlite.Connection,
    query: str,
    candidate_ids: set[str],
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

    # Fetch total doc count
    cursor = await conn.execute("SELECT COUNT(*) FROM code_node_text")
    row = await cursor.fetchone()
    n_docs: int = row[0] if row else 0

    terms = list(dict.fromkeys(_query_terms(query)))  # distinct, order-preserved

    # Fetch texts for candidates only
    placeholders = ",".join("?" * len(candidate_ids))
    cursor = await conn.execute(
        f"SELECT node_id, text FROM code_node_text WHERE node_id IN ({placeholders})",
        tuple(candidate_ids),
    )
    node_texts: dict[str, str] = {r[0]: r[1].lower() for r in await cursor.fetchall()}

    # Compute IDF for each term (df = count across ALL docs, not just candidates)
    term_idf: dict[str, float] = {}
    for term in terms:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM code_node_text WHERE lower(text) LIKE ?",
            (f"%{term}%",),
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
