"""Tests for archivum.db.graph — Kuzu graph DB operations."""
import pytest
from unittest.mock import MagicMock, call, patch

import archivum.db.graph as graph_module
from archivum.db import graph as graph


# ── Shared helpers ────────────────────────────────────────────────────────────


def make_row_result(*rows):
    """Return a mock Kuzu result that yields the given rows in order."""
    mock_result = MagicMock()
    rows_iter = iter(rows)
    remaining = [len(rows)]

    def has_next():
        return remaining[0] > 0

    def get_next():
        remaining[0] -= 1
        return next(rows_iter)

    mock_result.has_next.side_effect = has_next
    mock_result.get_next.side_effect = get_next
    return mock_result


def make_empty_result():
    """Return a mock Kuzu result with no rows."""
    mock_result = MagicMock()
    mock_result.has_next.return_value = False
    return mock_result


# ── Singleton reset fixture ───────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_graph_singleton():
    graph_module._conn = None
    graph_module._db = None
    yield
    graph_module._conn = None
    graph_module._db = None


# ── TestUpsertPage ────────────────────────────────────────────────────────────


class TestUpsertPage:
    async def test_smoke_upsert_page(self, mock_kuzu_conn):
        await graph.upsert_page("my-slug", "My Title", wiki_id="wiki1")
        assert mock_kuzu_conn.execute.called

    async def test_upsert_page_passes_slug(self, mock_kuzu_conn):
        await graph.upsert_page("hello-world", "Hello World", wiki_id="wiki1")
        args, kwargs = mock_kuzu_conn.execute.call_args
        # First arg is the query string
        assert "slug" in args[0]
        # Second arg is the parameters dict
        assert args[1]["slug"] == "hello-world"
        assert args[1]["title"] == "Hello World"
        assert args[1]["wiki_id"] == "wiki1"


# ── TestUpsertEntity ──────────────────────────────────────────────────────────


class TestUpsertEntity:
    async def test_smoke_upsert_entity(self, mock_kuzu_conn):
        await graph.upsert_entity("London", "place", wiki_id="wiki1")
        assert mock_kuzu_conn.execute.called

    async def test_upsert_entity_passes_type(self, mock_kuzu_conn):
        await graph.upsert_entity("Newton", "person", wiki_id="wiki1")
        args, kwargs = mock_kuzu_conn.execute.call_args
        assert args[1]["name"] == "Newton"
        assert args[1]["type"] == "person"
        assert args[1]["wiki_id"] == "wiki1"


# ── TestAddReference ──────────────────────────────────────────────────────────


class TestAddReference:
    async def test_smoke_add_reference(self, mock_kuzu_conn):
        await graph.add_reference("page-a", "page-b", wiki_id="wiki1")
        assert mock_kuzu_conn.execute.called

    async def test_add_reference_passes_slugs(self, mock_kuzu_conn):
        await graph.add_reference("src-slug", "dst-slug", wiki_id="wiki1")
        args, kwargs = mock_kuzu_conn.execute.call_args
        assert args[1]["from_slug"] == "src-slug"
        assert args[1]["to_slug"] == "dst-slug"

    async def test_add_reference_exception_is_swallowed(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.side_effect = RuntimeError("kuzu boom")
        # Should not raise
        await graph.add_reference("a", "b", wiki_id="wiki1")


# ── TestAddMention ────────────────────────────────────────────────────────────


class TestAddMention:
    async def test_smoke_add_mention(self, mock_kuzu_conn):
        await graph.add_mention("my-page", "Some Entity", wiki_id="wiki1")
        assert mock_kuzu_conn.execute.called

    async def test_add_mention_exception_is_swallowed(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.side_effect = RuntimeError("kuzu boom")
        await graph.add_mention("page", "entity", wiki_id="wiki1")


# ── TestAddEntityRelation ─────────────────────────────────────────────────────


class TestAddEntityRelation:
    async def test_smoke_add_entity_relation(self, mock_kuzu_conn):
        await graph.add_entity_relation("Newton", "Gravity", wiki_id="wiki1")
        assert mock_kuzu_conn.execute.called

    async def test_add_entity_relation_exception_is_swallowed(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.side_effect = RuntimeError("kuzu boom")
        await graph.add_entity_relation("A", "B", wiki_id="wiki1")


# ── TestGetBacklinks ──────────────────────────────────────────────────────────


class TestGetBacklinks:
    async def test_returns_empty_list_when_no_rows(self, mock_kuzu_conn):
        # Default mock_kuzu_conn has has_next() == False
        result = await graph.get_backlinks("target-slug", wiki_id="wiki1")
        assert result == []

    async def test_returns_backlink_data_when_rows_exist(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.return_value = make_row_result(
            ("other-page", "Other Page")
        )
        result = await graph.get_backlinks("target-slug", wiki_id="wiki1")
        assert len(result) == 1
        assert result[0]["slug"] == "other-page"
        assert result[0]["title"] == "Other Page"

    async def test_returns_multiple_backlinks(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.return_value = make_row_result(
            ("page-a", "Page A"),
            ("page-b", "Page B"),
        )
        result = await graph.get_backlinks("target", wiki_id="wiki1")
        assert len(result) == 2
        slugs = {r["slug"] for r in result}
        assert slugs == {"page-a", "page-b"}

    async def test_returns_empty_list_on_exception(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.side_effect = RuntimeError("kuzu boom")
        result = await graph.get_backlinks("target", wiki_id="wiki1")
        assert result == []


# ── TestGetNeighbors ──────────────────────────────────────────────────────────


class TestGetNeighbors:
    async def test_returns_center_node_id(self, mock_kuzu_conn):
        # All queries return empty — just check center key is set
        result = await graph.get_neighbors("my-node", wiki_id="wiki1")
        assert result["center"] == "my-node"

    async def test_returns_empty_nodes_when_no_rows(self, mock_kuzu_conn):
        result = await graph.get_neighbors("my-node", wiki_id="wiki1")
        assert result["nodes"] == []
        assert result["edges"] == []

    async def test_deduplicates_nodes(self, mock_kuzu_conn):
        # Simulate page-references query returning a node, then backlinks returning same node.
        # get_neighbors makes 4 execute() calls in sequence.
        # We return the same neighbor from queries 1 and 2, empty for 3 and 4.
        call_index = {"n": 0}

        def execute_side_effect(query, params=None):
            call_index["n"] += 1
            n = call_index["n"]
            if n == 1:
                # Forward references: center -> neighbor-1
                return make_row_result(("my-node", "neighbor-1", "Neighbor One"))
            elif n == 2:
                # Backlinks: neighbor-1 -> center (same neighbor-1 node)
                return make_row_result(("neighbor-1", "Neighbor One"))
            else:
                return make_empty_result()

        mock_kuzu_conn.execute.side_effect = execute_side_effect

        result = await graph.get_neighbors("my-node", wiki_id="wiki1")
        # Despite appearing in 2 queries, neighbor-1 should be deduped
        node_ids = [n["id"] for n in result["nodes"]]
        assert node_ids.count("neighbor-1") == 1
        # Edges are NOT deduped — we get one edge per query result
        assert len(result["edges"]) == 2


# ── TestGetAllNodesEdges ──────────────────────────────────────────────────────


class TestGetAllNodesEdges:
    async def test_returns_nodes_and_edges_keys(self, mock_kuzu_conn):
        result = await graph.get_all_nodes_edges(wiki_id="wiki1")
        assert "nodes" in result
        assert "edges" in result

    async def test_returns_empty_when_no_rows(self, mock_kuzu_conn):
        result = await graph.get_all_nodes_edges(wiki_id="wiki1")
        assert result["nodes"] == []
        assert result["edges"] == []

    async def test_filters_by_wiki_id(self, mock_kuzu_conn):
        # get_all_nodes_edges makes 5 execute() calls: pages, entities,
        # REFERENCES edges, MENTIONS edges, RELATED_TO edges.
        # Return one page row with wrong wiki_id, one with correct wiki_id.
        call_index = {"n": 0}

        def execute_side_effect(query, params=None):
            call_index["n"] += 1
            n = call_index["n"]
            if n == 1:
                # Pages query: two rows, only second matches wiki1
                return make_row_result(
                    ("page-wrong", "Wrong Wiki Page", "other-wiki"),
                    ("page-right", "Right Wiki Page", "wiki1"),
                )
            else:
                return make_empty_result()

        mock_kuzu_conn.execute.side_effect = execute_side_effect

        result = await graph.get_all_nodes_edges(wiki_id="wiki1")
        node_ids = [n["id"] for n in result["nodes"]]
        assert "page-right" in node_ids
        assert "page-wrong" not in node_ids

    async def test_includes_edges_for_matching_wiki(self, mock_kuzu_conn):
        call_index = {"n": 0}

        def execute_side_effect(query, params=None):
            call_index["n"] += 1
            n = call_index["n"]
            if n == 1:
                # Pages: two matching pages
                return make_row_result(
                    ("page-a", "Page A", "wiki1"),
                    ("page-b", "Page B", "wiki1"),
                )
            elif n == 3:
                # REFERENCES edges
                return make_row_result(("page-a", "page-b", "wiki1"))
            else:
                return make_empty_result()

        mock_kuzu_conn.execute.side_effect = execute_side_effect

        result = await graph.get_all_nodes_edges(wiki_id="wiki1")
        assert len(result["edges"]) == 1
        assert result["edges"][0]["from"] == "page-a"
        assert result["edges"][0]["to"] == "page-b"


# ── TestDeletePageNode ────────────────────────────────────────────────────────


class TestDeletePageNode:
    async def test_smoke_delete_page_node(self, mock_kuzu_conn):
        await graph.delete_page_node("my-slug")
        assert mock_kuzu_conn.execute.called

    async def test_delete_passes_slug(self, mock_kuzu_conn):
        await graph.delete_page_node("target-slug")
        args, kwargs = mock_kuzu_conn.execute.call_args
        assert args[1]["slug"] == "target-slug"

    async def test_delete_exception_is_swallowed(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.side_effect = RuntimeError("kuzu boom")
        # Should not raise
        await graph.delete_page_node("target-slug")


# ── TestCleanupAbandonedNodes ─────────────────────────────────────────────────


class TestCleanupAbandonedNodes:
    async def test_returns_deleted_count(self, mock_kuzu_conn):
        # First execute() call returns COUNT row, second is the DELETE (no rows needed)
        call_index = {"n": 0}

        def execute_side_effect(query, params=None):
            call_index["n"] += 1
            n = call_index["n"]
            if n == 1:
                return make_row_result((3,))
            else:
                return make_empty_result()

        mock_kuzu_conn.execute.side_effect = execute_side_effect

        result = await graph.cleanup_abandoned_nodes(wiki_id="wiki1")
        assert result == {"deleted_entities": 3}

    async def test_returns_zero_when_no_rows(self, mock_kuzu_conn):
        # has_next() returns False — count query yields nothing
        result = await graph.cleanup_abandoned_nodes(wiki_id="wiki1")
        assert result == {"deleted_entities": 0}

    async def test_returns_zero_on_exception(self, mock_kuzu_conn):
        mock_kuzu_conn.execute.side_effect = RuntimeError("kuzu boom")
        result = await graph.cleanup_abandoned_nodes(wiki_id="wiki1")
        assert result == {"deleted_entities": 0}
