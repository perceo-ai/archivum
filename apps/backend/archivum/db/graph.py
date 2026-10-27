"""Kuzu embedded graph-DB wrapper.

All kuzu calls are synchronous; they are wrapped in asyncio.run_in_executor
so they don't block the event loop.

Kuzu is an embedded, single-process database: while one process holds the
file, no other process can open it, read-only or not. So exactly one process
(``kuzu_role="owner"``, the API) opens it. Any other process that needs the
graph (``kuzu_role="client"``, the MCP server) sends each call to the owner's
``/internal/graph/{op}`` endpoint instead. Every public function below is a
dispatcher over a ``_local_*`` twin that does the real work on the owner.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import kuzu

from archivum.config import Settings, get_settings

logger = logging.getLogger(__name__)

class GraphUnavailableError(RuntimeError):
    """Raised when the graph backend cannot serve a request.

    No caller should ever see a raw kuzu IOException or an httpx
    connection error — both get normalized to this."""


# ── Singleton database handle ─────────────────────────────────────────────────

_db: kuzu.Database | None = None


def _get_conn(settings: Settings | None = None) -> kuzu.Connection:
    """A fresh connection on the one shared database, for a single operation.

    Not a shared connection: a kuzu Connection keeps every statement it ever
    prepared until it is closed, and every parameterized execute() prepares
    one, so a connection held for the life of the process grew without bound.
    Connections are cheap; the Database is the expensive, single handle.
    """
    global _db
    if _db is None:
        s = settings or get_settings()
        kuzu_path = Path(s.kuzu_path)
        # kuzu.Database expects a database *file path* in current kuzu-python.
        # We store it under the configured directory.
        kuzu_path.mkdir(parents=True, exist_ok=True)
        db_file = kuzu_path / "archivum.kuzu"
        # Each committed write keeps in-memory version state until the next
        # checkpoint, hundreds of times the bytes it adds to the WAL. Kuzu's own
        # threshold is WAL size (16 MB), which left gigabytes resident first.
        _db = kuzu.Database(str(db_file), checkpoint_threshold=s.kuzu_checkpoint_threshold_bytes)
        _init_schema(kuzu.Connection(_db))
    return kuzu.Connection(_db)


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
        """CREATE NODE TABLE IF NOT EXISTS KnowledgeNode(
            id STRING,
            label STRING,
            kind STRING,
            scope STRING,
            wiki_id STRING,
            confidence DOUBLE,
            extraction_method STRING,
            citations STRING,
            PRIMARY KEY (id)
        )""",
        # Relationship tables
        "CREATE REL TABLE IF NOT EXISTS REFERENCES(FROM Page TO Page)",
        "CREATE REL TABLE IF NOT EXISTS MENTIONS(FROM Page TO Entity)",
        "CREATE REL TABLE IF NOT EXISTS RELATED_TO(FROM Entity TO Entity)",
        """CREATE REL TABLE IF NOT EXISTS KNOWLEDGE_RELATIONSHIP(
            FROM KnowledgeNode TO KnowledgeNode,
            id STRING,
            rel_type STRING,
            scope STRING,
            confidence DOUBLE,
            extraction_method STRING,
            citations STRING
        )""",
    ]
    for stmt in ddl_statements:
        try:
            conn.execute(stmt)
        except Exception as exc:
            # Table already exists errors are safe to ignore
            if "already exists" not in str(exc).lower():
                logger.warning("Kuzu DDL warning: %s — %s", stmt[:60], exc)


_LOCK_RETRY_DELAYS = (0.1, 0.3, 0.9)


def _execute_with_retry(conn: kuzu.Connection, query: str, params: dict[str, Any] | None = None):
    """Run one query, riding out brief lock contention inside the owner.

    This is not what keeps two processes apart — only the owner ever opens
    the file. It covers the transient case within that one process, such as
    a schema-init race on cold start.
    """
    for attempt, delay in enumerate(_LOCK_RETRY_DELAYS, start=1):
        try:
            if params is None:
                return conn.execute(query)
            return conn.execute(query, params)
        except Exception as exc:
            if "lock" not in str(exc).lower():
                raise
            if attempt == len(_LOCK_RETRY_DELAYS):
                raise GraphUnavailableError(
                    f"Kuzu still locked after {attempt} attempts: {exc}"
                ) from exc
            logger.warning("Kuzu lock contention (attempt %d): %s", attempt, exc)
            time.sleep(delay)


# ── Async wrappers ────────────────────────────────────────────────────────────

# One operation at a time. Kuzu refuses a second concurrent write transaction
# rather than waiting for it, and connections are per operation, so nothing
# inside kuzu serializes them any more; this does, as the shared one used to.
_ops_lock = threading.Lock()


def _serialized(fn, *args, **kwargs):
    with _ops_lock:
        return fn(*args, **kwargs)


async def _run(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _serialized(fn, *args, **kwargs))


# ── Client role: calls go to the owner ────────────────────────────────────────

_RPC_TIMEOUT_SECONDS = 10.0
# Tests point this at an in-process transport; production leaves it None.
_rpc_client_override: httpx.AsyncClient | None = None


def _is_client_role() -> bool:
    return get_settings().kuzu_role == "client"


async def _rpc_call(op: str, **kwargs) -> Any:
    settings = get_settings()
    url = f"{settings.graph_rpc_url.rstrip('/')}/internal/graph/{op}"
    headers = {}
    if settings.internal_graph_token:
        headers["X-Internal-Token"] = settings.internal_graph_token
    try:
        if _rpc_client_override is not None:
            response = await _rpc_client_override.post(url, json=kwargs, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=_RPC_TIMEOUT_SECONDS) as client:
                response = await client.post(url, json=kwargs, headers=headers)
    except httpx.HTTPError as exc:
        raise GraphUnavailableError(f"graph {op}: owner unreachable at {url}: {exc!r}") from exc
    if not response.is_success:
        raise GraphUnavailableError(
            f"graph {op}: owner answered {response.status_code}: {response.text[:500]}"
        )
    try:
        return response.json()["result"]
    except (ValueError, KeyError, TypeError) as exc:
        raise GraphUnavailableError(f"graph {op}: malformed owner response: {exc!r}") from exc


# ── Public API ────────────────────────────────────────────────────────────────

async def init_graph(settings: Settings | None = None) -> None:
    """Initialize the Kuzu database and schema (call at startup).

    A client never opens the file. It does not check the owner here either:
    compose starts it as soon as the owner starts, not once it is healthy, so
    reachability is found out on the first real call.
    """
    s = settings or get_settings()
    if s.kuzu_role == "client":
        logger.info("Kuzu graph in client mode; graph calls go to %s", s.graph_rpc_url)
        return
    await _run(_get_conn, settings)
    logger.info("Kuzu graph initialized")


async def _local_upsert_page(slug: str, title: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        # MERGE semantics: delete + re-insert if exists
        _execute_with_retry(
            conn,
            "MERGE (p:Page {slug: $slug}) SET p.title = $title, p.wiki_id = $wiki_id",
            {"slug": slug, "title": title, "wiki_id": wiki_id},
        )
    await _run(_do)


async def _local_upsert_entity(name: str, entity_type: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        _execute_with_retry(
            conn,
            "MERGE (e:Entity {name: $name}) SET e.type = $type, e.wiki_id = $wiki_id",
            {"name": name, "type": entity_type, "wiki_id": wiki_id},
        )
    await _run(_do)


async def _local_upsert_knowledge_node(
    node_id: str,
    label: str,
    kind: str,
    scope: str,
    confidence: float,
    extraction_method: str,
    citations: list[dict[str, Any]],
    wiki_id: str = "default",
) -> None:
    """Upsert a canonical object in the rebuildable knowledge projection."""
    def _do():
        conn = _get_conn()
        _execute_with_retry(
            conn,
            "MERGE (n:KnowledgeNode {id: $id}) "
            "SET n.label = $label, n.kind = $kind, n.scope = $scope, "
            "n.wiki_id = $wiki_id, n.confidence = $confidence, "
            "n.extraction_method = $extraction_method, n.citations = $citations",
            {
                "id": node_id,
                "label": label,
                "kind": kind,
                "scope": scope,
                "wiki_id": wiki_id,
                "confidence": confidence,
                "extraction_method": extraction_method,
                "citations": json.dumps(citations),
            },
        )
    await _run(_do)


async def _local_add_knowledge_relationship(
    src_id: str,
    dst_id: str,
    relationship_id: str,
    rel_type: str,
    scope: str,
    confidence: float,
    extraction_method: str,
    citations: list[dict[str, Any]],
) -> None:
    """Project a canonical relationship with its provenance metadata."""
    def _do():
        conn = _get_conn()
        _execute_with_retry(
            conn,
            "MATCH (a:KnowledgeNode {id: $src_id}), (b:KnowledgeNode {id: $dst_id}) "
            "MERGE (a)-[r:KNOWLEDGE_RELATIONSHIP {id: $id}]->(b) "
            "SET r.rel_type = $rel_type, r.scope = $scope, r.confidence = $confidence, "
            "r.extraction_method = $extraction_method, r.citations = $citations",
            {
                "src_id": src_id,
                "dst_id": dst_id,
                "id": relationship_id,
                "rel_type": rel_type,
                "scope": scope,
                "confidence": confidence,
                "extraction_method": extraction_method,
                "citations": json.dumps(citations),
            },
        )
    await _run(_do)


async def _local_clear_knowledge_projection(wiki_id: str = "default") -> None:
    """Remove a wiki's generic canonical projection before rebuilding it."""
    def _do():
        conn = _get_conn()
        _execute_with_retry(
            conn,
            "MATCH (n:KnowledgeNode {wiki_id: $wiki_id}) DETACH DELETE n",
            {"wiki_id": wiki_id},
        )
    await _run(_do)


async def _local_clear_legacy_projection(wiki_id: str = "default") -> None:
    """Remove a wiki's legacy Page and Entity projection before rebuilding it."""
    def _do():
        conn = _get_conn()
        _execute_with_retry(
            conn,
            "MATCH (p:Page {wiki_id: $wiki_id}) DETACH DELETE p",
            {"wiki_id": wiki_id},
        )
        _execute_with_retry(
            conn,
            "MATCH (e:Entity {wiki_id: $wiki_id}) DETACH DELETE e",
            {"wiki_id": wiki_id},
        )
    await _run(_do)


async def _local_add_reference(from_slug: str, to_slug: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        try:
            _execute_with_retry(
                conn,
                "MATCH (a:Page {slug: $from_slug}), (b:Page {slug: $to_slug}) "
                "MERGE (a)-[:REFERENCES]->(b)",
                {"from_slug": from_slug, "to_slug": to_slug},
            )
        except Exception as exc:
            logger.debug("add_reference warning: %s", exc)
    await _run(_do)


async def _local_clear_references_from_page(slug: str, wiki_id: str = "default") -> None:
    """Remove all outgoing REFERENCES edges for a page before rebuilding them."""
    def _do():
        conn = _get_conn()
        try:
            _execute_with_retry(
                conn,
                "MATCH (p:Page {slug: $slug})-[r:REFERENCES]->(:Page) DELETE r",
                {"slug": slug},
            )
        except Exception as exc:
            logger.debug("clear_references_from_page warning: %s", exc)

    await _run(_do)


async def _local_add_mention(page_slug: str, entity_name: str, wiki_id: str = "default") -> None:
    def _do():
        conn = _get_conn()
        try:
            _execute_with_retry(
                conn,
                "MATCH (p:Page {slug: $slug}), (e:Entity {name: $name}) "
                "MERGE (p)-[:MENTIONS]->(e)",
                {"slug": page_slug, "name": entity_name},
            )
        except Exception as exc:
            logger.debug("add_mention warning: %s", exc)
    await _run(_do)


async def _local_add_entity_relation(
    from_name: str, to_name: str, wiki_id: str = "default"
) -> None:
    def _do():
        conn = _get_conn()
        try:
            _execute_with_retry(
                conn,
                "MATCH (a:Entity {name: $from_name}), (b:Entity {name: $to_name}) "
                "MERGE (a)-[:RELATED_TO]->(b)",
                {"from_name": from_name, "to_name": to_name},
            )
        except Exception as exc:
            logger.debug("add_entity_relation warning: %s", exc)
    await _run(_do)


async def _local_get_neighbors(node_id: str, wiki_id: str = "default") -> dict[str, Any]:
    """Return nodes + edges 1 hop from *node_id* (works for both Page and Entity)."""
    def _do() -> dict[str, Any]:
        conn = _get_conn()
        nodes: list[dict] = []
        edges: list[dict] = []

        # Page references
        try:
            res = _execute_with_retry(
                conn,
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
            res = _execute_with_retry(
                conn,
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
            res = _execute_with_retry(
                conn,
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
            res = _execute_with_retry(
                conn,
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


async def _local_get_backlinks(slug: str, wiki_id: str = "default") -> list[dict[str, Any]]:
    """Return all Page nodes that have a REFERENCES edge pointing to *slug*."""
    def _do() -> list[dict]:
        conn = _get_conn()
        results = []
        try:
            res = _execute_with_retry(
                conn,
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


async def _local_get_all_nodes_edges(wiki_id: str = "default") -> dict[str, Any]:
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
            res = _execute_with_retry(conn, "MATCH (p:Page) RETURN p.slug, p.title, p.wiki_id")
            while res.has_next():
                row = res.get_next()
                if row[2] == wiki_id:
                    _add_node(row[0], row[1], "page")
        except Exception as exc:
            logger.debug("get_all pages error: %s", exc)

        # All entities
        try:
            res = _execute_with_retry(conn, "MATCH (e:Entity) RETURN e.name, e.type, e.wiki_id")
            while res.has_next():
                row = res.get_next()
                if row[2] == wiki_id:
                    _add_node(row[0], row[0], "entity", entity_type=row[1])
        except Exception as exc:
            logger.debug("get_all entities error: %s", exc)

        # All REFERENCES edges
        try:
            res = _execute_with_retry(
                conn,
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
            res = _execute_with_retry(
                conn,
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
            res = _execute_with_retry(
                conn,
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


async def _local_delete_page_node(slug: str) -> None:
    """Remove a Page node and all its edges from the graph."""
    def _do():
        conn = _get_conn()
        try:
            _execute_with_retry(conn, "MATCH (p:Page {slug: $slug}) DETACH DELETE p", {"slug": slug})
        except Exception as exc:
            logger.debug("delete_page_node error: %s", exc)
    await _run(_do)


async def _local_rename_page_node(old_slug: str, new_slug: str, wiki_id: str = "default") -> None:
    """Rename a Page node while preserving graph edges where Kuzu supports SET."""
    def _do():
        conn = _get_conn()
        try:
            _execute_with_retry(
                conn,
                "MATCH (p:Page {slug: $old_slug}) SET p.slug = $new_slug, p.wiki_id = $wiki_id",
                {"old_slug": old_slug, "new_slug": new_slug, "wiki_id": wiki_id},
            )
        except Exception as exc:
            logger.debug("rename_page_node error: %s", exc)
    await _run(_do)


async def _local_cleanup_abandoned_nodes(wiki_id: str = "default") -> dict[str, int]:
    """
    Delete graph nodes that no longer have any backing Page.

    Today this means Entity nodes that have no incoming MENTIONS edge from any
    Page in the same wiki_id (typically after a page delete).
    """

    def _do() -> dict[str, int]:
        conn = _get_conn()
        deleted_entities = 0
        try:
            res = _execute_with_retry(
                conn,
                "MATCH (e:Entity) "
                "WHERE e.wiki_id = $wiki_id "
                "AND NOT EXISTS { MATCH (:Page {wiki_id: $wiki_id})-[:MENTIONS]->(e) } "
                "RETURN COUNT(e)",
                {"wiki_id": wiki_id},
            )
            if res.has_next():
                row = res.get_next()
                deleted_entities = int(row[0] or 0)
        except Exception as exc:
            logger.debug("cleanup_abandoned_nodes count error: %s", exc)

        try:
            _execute_with_retry(
                conn,
                "MATCH (e:Entity) "
                "WHERE e.wiki_id = $wiki_id "
                "AND NOT EXISTS { MATCH (:Page {wiki_id: $wiki_id})-[:MENTIONS]->(e) } "
                "DETACH DELETE e",
                {"wiki_id": wiki_id},
            )
        except Exception as exc:
            logger.debug("cleanup_abandoned_nodes delete error: %s", exc)

        return {"deleted_entities": deleted_entities}

    return await _run(_do)


# ── Dispatchers: owner runs locally, client asks the owner ────────────────────

async def upsert_page(slug: str, title: str, wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("upsert_page", slug=slug, title=title, wiki_id=wiki_id)
    return await _local_upsert_page(slug, title, wiki_id)


async def upsert_entity(name: str, entity_type: str, wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("upsert_entity", name=name, entity_type=entity_type, wiki_id=wiki_id)
    return await _local_upsert_entity(name, entity_type, wiki_id)


async def upsert_knowledge_node(
    node_id: str,
    label: str,
    kind: str,
    scope: str,
    confidence: float,
    extraction_method: str,
    citations: list[dict[str, Any]],
    wiki_id: str = "default",
) -> None:
    if _is_client_role():
        return await _rpc_call(
            "upsert_knowledge_node",
            node_id=node_id,
            label=label,
            kind=kind,
            scope=scope,
            confidence=confidence,
            extraction_method=extraction_method,
            citations=citations,
            wiki_id=wiki_id,
        )
    return await _local_upsert_knowledge_node(
        node_id, label, kind, scope, confidence, extraction_method, citations, wiki_id
    )


async def add_knowledge_relationship(
    src_id: str,
    dst_id: str,
    relationship_id: str,
    rel_type: str,
    scope: str,
    confidence: float,
    extraction_method: str,
    citations: list[dict[str, Any]],
) -> None:
    if _is_client_role():
        return await _rpc_call(
            "add_knowledge_relationship",
            src_id=src_id,
            dst_id=dst_id,
            relationship_id=relationship_id,
            rel_type=rel_type,
            scope=scope,
            confidence=confidence,
            extraction_method=extraction_method,
            citations=citations,
        )
    return await _local_add_knowledge_relationship(
        src_id, dst_id, relationship_id, rel_type, scope, confidence, extraction_method, citations
    )


async def clear_knowledge_projection(wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("clear_knowledge_projection", wiki_id=wiki_id)
    return await _local_clear_knowledge_projection(wiki_id)


async def clear_legacy_projection(wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("clear_legacy_projection", wiki_id=wiki_id)
    return await _local_clear_legacy_projection(wiki_id)


async def add_reference(from_slug: str, to_slug: str, wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("add_reference", from_slug=from_slug, to_slug=to_slug, wiki_id=wiki_id)
    return await _local_add_reference(from_slug, to_slug, wiki_id)


async def clear_references_from_page(slug: str, wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("clear_references_from_page", slug=slug, wiki_id=wiki_id)
    return await _local_clear_references_from_page(slug, wiki_id)


async def add_mention(page_slug: str, entity_name: str, wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("add_mention", page_slug=page_slug, entity_name=entity_name, wiki_id=wiki_id)
    return await _local_add_mention(page_slug, entity_name, wiki_id)


async def add_entity_relation(
    from_name: str, to_name: str, wiki_id: str = "default"
) -> None:
    if _is_client_role():
        return await _rpc_call("add_entity_relation", from_name=from_name, to_name=to_name, wiki_id=wiki_id)
    return await _local_add_entity_relation(from_name, to_name, wiki_id)


async def get_neighbors(node_id: str, wiki_id: str = "default") -> dict[str, Any]:
    if _is_client_role():
        return await _rpc_call("get_neighbors", node_id=node_id, wiki_id=wiki_id)
    return await _local_get_neighbors(node_id, wiki_id)


async def get_backlinks(slug: str, wiki_id: str = "default") -> list[dict[str, Any]]:
    if _is_client_role():
        return await _rpc_call("get_backlinks", slug=slug, wiki_id=wiki_id)
    return await _local_get_backlinks(slug, wiki_id)


async def get_all_nodes_edges(wiki_id: str = "default") -> dict[str, Any]:
    if _is_client_role():
        return await _rpc_call("get_all_nodes_edges", wiki_id=wiki_id)
    return await _local_get_all_nodes_edges(wiki_id)


async def delete_page_node(slug: str) -> None:
    if _is_client_role():
        return await _rpc_call("delete_page_node", slug=slug)
    return await _local_delete_page_node(slug)


async def rename_page_node(old_slug: str, new_slug: str, wiki_id: str = "default") -> None:
    if _is_client_role():
        return await _rpc_call("rename_page_node", old_slug=old_slug, new_slug=new_slug, wiki_id=wiki_id)
    return await _local_rename_page_node(old_slug, new_slug, wiki_id)


async def cleanup_abandoned_nodes(wiki_id: str = "default") -> dict[str, int]:
    if _is_client_role():
        return await _rpc_call("cleanup_abandoned_nodes", wiki_id=wiki_id)
    return await _local_cleanup_abandoned_nodes(wiki_id)
