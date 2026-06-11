"""Tests for GET /api/graph and GET /api/graph/neighbors."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class TestGraphEndpoint(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.token = create_access_token("owner", "owner", "default", self.settings)
        with (
            patch("archivum.main.sqlite.init_db", new=AsyncMock()),
            patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
            patch("archivum.main.graph.init_graph", new=AsyncMock()),
            patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
        ):
            self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)
        self.client.cookies.set("access_token", self.token)

    def test_get_graph_returns_nodes_and_edges(self):
        """GET /api/graph returns nodes and edges from the graph store."""
        fake_data = {
            "nodes": [
                {"id": "page-a", "label": "Page A"},
                {"id": "page-b", "label": "Page B"},
            ],
            "edges": [
                {"from": "page-a", "to": "page-b", "type": "REFERENCES"},
            ],
        }
        with patch("archivum.api.graph.graph.get_all_nodes_edges", new=AsyncMock(return_value=fake_data)):
            response = self.client.get("/api/graph")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(len(data["edges"]), 1)

    def test_get_graph_transforms_edge_type_to_label(self):
        """Edges from the DB have `type`; the API transforms this to `label`."""
        fake_data = {
            "nodes": [{"id": "a", "label": "A"}],
            "edges": [
                {"from": "a", "to": "b", "type": "REFERENCES"},
            ],
        }
        with patch("archivum.api.graph.graph.get_all_nodes_edges", new=AsyncMock(return_value=fake_data)):
            response = self.client.get("/api/graph")

        self.assertEqual(response.status_code, 200)
        edge = response.json()["edges"][0]
        self.assertIn("label", edge)
        self.assertNotIn("type", edge)
        self.assertEqual(edge["label"], "REFERENCES")

    def test_get_graph_requires_auth(self):
        """Unauthenticated requests to /api/graph should return 401."""
        client_no_auth = TestClient(self.app, raise_server_exceptions=True)
        with patch("archivum.api.graph.graph.get_all_nodes_edges", new=AsyncMock(return_value={"nodes": [], "edges": []})):
            response = client_no_auth.get("/api/graph")

        self.assertEqual(response.status_code, 401)


class TestGraphNeighbors(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.token = create_access_token("owner", "owner", "default", self.settings)
        with (
            patch("archivum.main.sqlite.init_db", new=AsyncMock()),
            patch("archivum.main.qdrant.init_collection", new=AsyncMock()),
            patch("archivum.main.graph.init_graph", new=AsyncMock()),
            patch("archivum.main.sqlite.ensure_owner_exists", new=AsyncMock()),
        ):
            self.app = create_app()
        self.client = TestClient(self.app, raise_server_exceptions=True)
        self.client.cookies.set("access_token", self.token)

    def test_returns_center_and_neighbors(self):
        """GET /api/graph/neighbors returns center node and neighbor nodes/edges."""
        fake_data = {
            "center": {"id": "page-a", "label": "Page A"},
            "nodes": [
                {"id": "page-a", "label": "Page A"},
                {"id": "page-b", "label": "Page B"},
            ],
            "edges": [
                {"from": "page-a", "to": "page-b", "type": "REFERENCES"},
            ],
        }
        with patch("archivum.api.graph.graph.get_neighbors", new=AsyncMock(return_value=fake_data)):
            response = self.client.get("/api/graph/neighbors?node_id=page-a")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("center", data)
        self.assertEqual(data["center"]["id"], "page-a")
        self.assertEqual(len(data["nodes"]), 2)
        self.assertEqual(len(data["edges"]), 1)

    def test_transforms_edges_to_label(self):
        """Neighbor edges have `type` mapped to `label`."""
        fake_data = {
            "center": {"id": "x", "label": "X"},
            "nodes": [{"id": "x"}, {"id": "y"}],
            "edges": [{"from": "x", "to": "y", "type": "RELATED"}],
        }
        with patch("archivum.api.graph.graph.get_neighbors", new=AsyncMock(return_value=fake_data)):
            response = self.client.get("/api/graph/neighbors?node_id=x")

        self.assertEqual(response.status_code, 200)
        edge = response.json()["edges"][0]
        self.assertIn("label", edge)
        self.assertNotIn("type", edge)
        self.assertEqual(edge["label"], "RELATED")

    def test_requires_auth(self):
        """Unauthenticated requests to /api/graph/neighbors should return 401."""
        client_no_auth = TestClient(self.app, raise_server_exceptions=True)
        with patch("archivum.api.graph.graph.get_neighbors", new=AsyncMock(return_value={"center": None, "nodes": [], "edges": []})):
            response = client_no_auth.get("/api/graph/neighbors?node_id=x")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
