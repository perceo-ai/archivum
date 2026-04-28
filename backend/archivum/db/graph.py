"""Kuzu embedded graph-DB wrapper.

All kuzu calls are synchronous; they are wrapped in asyncio.run_in_executor
so they don't block the event loop.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import kuzu

from archivum.config import Settings, get_settings

logger = logging.getLogger(__name__)

# ── Singleton database handle ─────────────────────────────────────────────────

_db: kuzu.Database | None = None
_conn: kuzu.Connection | None = None


def _get_conn(settings: Settings | None = None) -> kuzu.Connection:
    global _db, _conn
    if _conn is None:
        s = settings or get_settings()
        kuzu_path = Path(s.kuzu_path)
        kuzu_path.mkdir(parents=True, exist_ok=True)
        _db = kuzu.Database(str(kuzu_path))
        _conn = kuzu.Connection(_db)
        _init_schema(_conn)
    return _conn


def _init_schema(conn: kuzu.Connection) -> None:
    """Create node/rel tables if they don't exist."""
    ddl_statements = [
        # Node tables
        """CREATE NODE TABLE IF NOT EXISTS Page(
            slug STRING,
            title STRING,
            wiki_id STRING,
            PRIMARY KEY (slug)
        )""",
        """CREATE NODE TABLE IF NOT EXISTS Entity(
            name STRING,
            type STRING,
            wiki_id STRING,
            PRIMARY KEY (name)
        )""",
        # Relationship tables
        "CREATE REL TABLE IF NOT EXISTS REFERENCES(FROM Page TO Page)",
        "CREATE REL TABLE IF NOT EXISTS MENTIONS(FROM Page TO Entity)",
        "CREATE REL TABLE IF NOT EXISTS RELATED_TO(FROM Entity TO Entity)",
    ]
    for stmt in ddl_statements:
        try:
            conn.execute(stmt)
        except Exception as exc:
            # Table already exists errors are safe to ignore
            if "already exists" not in str(exc).lower():
                logger.warning("Kuzu DDL warning: %s — %s", stmt[:60], exc)


# ── Async wrappers ────────────────────────────────────────────────────────────

async def _run(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))


# ── Public API ────────────────────────────────────────────────────────────────

async def init_graph(settings: Settings | None = None) -> None:
    """Initialize the Kuzu database and schema (call at startup)."""
    await _run(_get_conn, settings)
    logger.info("Kuzu graph initialized")


async def upsert_page(slug: str, title: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        # MERGE semantics: delete + re-insert if exists
        conn.execute(
            "MERGE (p:Page {slug: $slug}) SET p.title = $title, p.wiki_id = $wiki_id",
            {"slug": slug, "title": title, "wiki_id": wiki_id},
        )
    await _run(_do)


async def upsert_entity(name: str, entity_type: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        conn.execute(
            "MERGE (e:Entity {name: $name}) SET e.type = $type, e.wiki_id = $wiki_id",
            {"name": name, "type": entity_type, "wiki_id": wiki_id},
        )
    await _run(_do)


async def add_reference(from_slug: str, to_slug: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        try:
            conn.execute(
                "MATCH (a:Page {slug: $from_slug}), (b:Page {slug: $to_slug}) "
                "MERGE (a)-[:REFERENCES]->(b)",
                {"from_slug": from_slug, "to_slug": to_slug},
            )
        except Exception as exc:
            logger.debug("add_reference warning: %s", exc)
    await _run(_do)


async def add_mention(page_slug: str, entity_name: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        try:
            conn.execute(
                "MATCH (p:Page {slug: $slug}), (e:Entity {name: $name}) "
                "MERGE (p)-[:MENTIONS]->(e)",
                {"slug": page_slug, "name": entity_name},
            )
        except Exception as exc:
            logger.debug("add_mention warning: %s", exc)
    await _run(_do)


async def add_entity_relation(
    from_name: str, to_name: str, wiki_id: str = "default"
) -> None:
    def _do():
        conn = _get_conn()
        try:
            conn.execute(
                "MATCH (a:Entity {name: $from_name}), (b:Entity {name: $to_name}) "
                "MERGE (a)-[:RELATED_TO]->(b)",
                {"from_name": from_name, "to_name": to_name},
            )
        except Exception as exc:
            logger.debug("add_entity_relation warning: %s", exc)
    await _run(_do)


async def get_neighbors(node_id: str, wiki_id: str = "default") -> dict[str, Any]:
    """Return nodes + edges 1 hop from *node_id* (works for both Page and Entity)."""
    def _do() -> dict[str, Any]:
        conn = _get_conn()
        nodes: list[dict] = []
        edges: list[dict] = []

        # Page references
        try:
            res = conn.execute(
                "MATCH (p:Page {slug: $id})-[r:REFERENCES]->(q:Page) "
                "RETURN p.slug, q.slug, q.title",
                {"id": node_id},
            )
            while res.has_next():
                row = res.get_next()
                nodes.append({"id": row[1], "label": row[2], "type": "page"})
                edges.append({"from": row[0], "to": row[1], "type": "references"})
        except Exception:
            pass

        # Backlinks
        try:
            res = conn.execute(
                "MATCH (q:Page)-[r:REFERENCES]->(p:Page {slug: $id}) "
                "RETURN q.slug, q.title",
                {"id": node_id},
            )
            while res.has_next():
                row = res.get_next()
                nodes.append({"id": row[0], "label": row[1], "type": "page"})
                edges.append({"from": row[0], "to": node_id, "type": "references"})
        except Exception:
            pass

        # Mentions
        try:
            res = conn.execute(
                "MATCH (p:Page {slug: $id})-[r:MENTIONS]->(e:Entity) "
                "RETURN e.name, e.type",
                {"id": node_id},
            )
            while res.has_next():
                row = res.get_next()
                nodes.append({"id": row[0], "label": row[0], "type": "entity", "entity_type": row[1]})
                edges.append({"from": node_id, "to": row[0], "type": "mentions"})
        except Exception:
            pass

        # Entity neighbors
        try:
            res = conn.execute(
                "MATCH (e:Entity {name: $id})-[r:RELATED_TO]->(f:Entity) "
                "RETURN f.name, f.type",
                {"id": node_id},
            )
            while res.has_next():
                row = res.get_next()
                nodes.append({"id": row[0], "label": row[0], "type": "entity", "entity_type": row[1]})
                edges.append({"from": node_id, "to": row[0], "type": "related_to"})
        except Exception:
            pass

        # Deduplicate nodes by id
        seen_ids = set()
        unique_nodes = []
        for n in nodes:
            if n["id"] not in seen_ids:
                seen_ids.add(n["id"])
                unique_nodes.append(n)

        return {"center": node_id, "nodes": unique_nodes, "edges": edges}

    return await _run(_do)


async def get_backlinks(slug: str, wiki_id: str = "default") -> list[dict[str, Any]]:
    """Return all Page nodes that have a REFERENCES edge pointing to *slug*."""
    def _do() -> list[dict]:
        conn = _get_conn()
        results = []
        try:
            res = conn.execute(
                "MATCH (p:Page)-[:REFERENCES]->(q:Page {slug: $slug}) "
                "RETURN p.slug, p.title",
                {"slug": slug},
            )
            while res.has_next():
                row = res.get_next()
                results.append({"slug": row[0], "title": row[1]})
        except Exception as exc:
            logger.debug("get_backlinks error: %s", exc)
        return results

    return await _run(_do)


async def get_all_nodes_edges(wiki_id: str = "default") -> dict[str, Any]:
    """Return all nodes + edges for vis.js full-graph rendering."""
    def _do() -> dict[str, Any]:
        conn = _get_conn()
        nodes: list[dict] = []
        edges: list[dict] = []
        seen_nodes: set[str] = set()

        def _add_node(node_id: str, label: str, node_type: str, **extra):
            if node_id not in seen_nodes:
                seen_nodes.add(node_id)
                nodes.append({"id": node_id, "label": label, "type": node_type, **extra})

        # All pages
        try:
            res = conn.execute("MATCH (p:Page) RETURN p.slug, p.title, p.wiki_id")
            while res.has_next():
                row = res.get_next()
                if row[2] == wiki_id:
                    _add_node(row[0], row[1], "page")
        except Exception as exc:
            logger.debug("get_all pages error: %s", exc)

        # All entities
        try:
            res = conn.execute("MATCH (e:Entity) RETURN e.name, e.type, e.wiki_id")
            while res.has_next():
                row = res.get_next()
                if row[2] == wiki_id:
                    _add_node(row[0], row[0], "entity", entity_type=row[1])
        except Exception as exc:
            logger.debug("get_all entities error: %s", exc)

        # All REFERENCES edges
        try:
            res = conn.execute(
                "MATCH (p:Page)-[:REFERENCES]->(q:Page) "
                "RETURN p.slug, q.slug, p.wiki_id"
            )
            while res.has_next():
                row = res.get_next()
                if row[2] == wiki_id:
                    edges.append({"from": row[0], "to": row[1], "type": "references"})
        except Exception as exc:
            logger.debug("get_all references error: %s", exc)

        # All MENTIONS edges
        try:
            res = conn.execute(
                "MATCH (p:Page)-[:MENTIONS]->(e:Entity) "
                "RETURN p.slug, e.name, p.wiki_id"
            )
            while res.has_next():
                row = res.get_next()
                if row[2] == wiki_id:
                    edges.append({"from": row[0], "to": row[1], "type": "mentions"})
        except Exception as exc:
            logger.debug("get_all mentions error: %s", exc)

        # All RELATED_TO edges
        try:
            res = conn.execute(
                "MATCH (a:Entity)-[:RELATED_TO]->(b:Entity) "
                "RETURN a.name, b.name, a.wiki_id"
            )
            while res.has_next():
                row = res.get_next()
                if row[2] == wiki_id:
                    edges.append({"from": row[0], "to": row[1], "type": "related_to"})
        except Exception as exc:
            logger.debug("get_all related_to error: %s", exc)

        return {"nodes": nodes, "edges": edges}

    return await _run(_do)


async def delete_page_node(slug: str) -> None:
    """Remove a Page node and all its edges from the graph."""
    def _do():
        conn = _get_conn()
        try:
            conn.execute("MATCH (p:Page {slug: $slug}) DETACH DELETE p", {"slug": slug})
        except Exception as exc:
            logger.debug("delete_page_node error: %s", exc)
    await _run(_do)
