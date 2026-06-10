"""Tests for GET /api/search."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class TestSearchEndpoint(unittest.TestCase):
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

    def test_returns_qdrant_results(self):
        """When qdrant returns enough results, return them directly."""
        fake_results = [
            {"slug": f"page-{i}", "title": f"Page {i}", "excerpt": "...", "score": 0.9 - i * 0.1}
            for i in range(5)
        ]
        with (
            patch("archivum.api.search.qdrant.search", new=AsyncMock(return_value=fake_results)),
            patch("archivum.api.search.sqlite.search_pages_fts", new=AsyncMock(return_value=[])),
        ):
            response = self.client.get("/api/search?q=hello")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 5)
        self.assertEqual(data[0]["slug"], "page-0")

    def test_falls_back_to_fts_when_qdrant_empty(self):
        """When qdrant returns no results, FTS results fill in."""
        fts_results = [
            {"slug": "fts-page", "title": "FTS Page", "excerpt": "keyword match"},
        ]
        with (
            patch("archivum.api.search.qdrant.search", new=AsyncMock(return_value=[])),
            patch("archivum.api.search.sqlite.search_pages_fts", new=AsyncMock(return_value=fts_results)),
        ):
            response = self.client.get("/api/search?q=keyword")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "fts-page")
        self.assertEqual(data[0]["score"], 0.0)

    def test_combines_qdrant_and_fts_results(self):
        """When qdrant returns fewer than threshold, FTS fills the rest."""
        qdrant_results = [
            {"slug": "qdrant-1", "title": "Qdrant One", "excerpt": "", "score": 0.8},
            {"slug": "qdrant-2", "title": "Qdrant Two", "excerpt": "", "score": 0.7},
        ]
        fts_results = [
            {"slug": "fts-1", "title": "FTS One", "excerpt": "match"},
            {"slug": "fts-2", "title": "FTS Two", "excerpt": "match"},
        ]
        with (
            patch("archivum.api.search.qdrant.search", new=AsyncMock(return_value=qdrant_results)),
            patch("archivum.api.search.sqlite.search_pages_fts", new=AsyncMock(return_value=fts_results)),
        ):
            response = self.client.get("/api/search?q=test")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        slugs = [d["slug"] for d in data]
        self.assertIn("qdrant-1", slugs)
        self.assertIn("fts-1", slugs)

    def test_requires_auth(self):
        """Requests without a token should return 401."""
        client_no_auth = TestClient(self.app, raise_server_exceptions=True)
        with (
            patch("archivum.api.search.qdrant.search", new=AsyncMock(return_value=[])),
            patch("archivum.api.search.sqlite.search_pages_fts", new=AsyncMock(return_value=[])),
        ):
            response = client_no_auth.get("/api/search?q=hello")

        self.assertEqual(response.status_code, 401)

    def test_deduplicates_by_slug(self):
        """FTS results whose slugs already appear in qdrant results are dropped."""
        qdrant_results = [
            {"slug": "shared-slug", "title": "From Qdrant", "excerpt": "", "score": 0.9},
        ]
        fts_results = [
            {"slug": "shared-slug", "title": "From FTS", "excerpt": "dup"},
            {"slug": "unique-fts", "title": "Unique FTS", "excerpt": "unique"},
        ]
        with (
            patch("archivum.api.search.qdrant.search", new=AsyncMock(return_value=qdrant_results)),
            patch("archivum.api.search.sqlite.search_pages_fts", new=AsyncMock(return_value=fts_results)),
        ):
            response = self.client.get("/api/search?q=dup")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        slugs = [d["slug"] for d in data]
        # shared-slug should appear exactly once
        self.assertEqual(slugs.count("shared-slug"), 1)
        # The qdrant version should win (higher score)
        shared = next(d for d in data if d["slug"] == "shared-slug")
        self.assertEqual(shared["score"], 0.9)

    def test_respects_limit_param(self):
        """Results are capped at the requested limit."""
        fts_results = [
            {"slug": f"page-{i}", "title": f"Page {i}", "excerpt": ""}
            for i in range(20)
        ]
        with (
            patch("archivum.api.search.qdrant.search", new=AsyncMock(return_value=[])),
            patch("archivum.api.search.sqlite.search_pages_fts", new=AsyncMock(return_value=fts_results)),
        ):
            response = self.client.get("/api/search?q=test&limit=5")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertLessEqual(len(data), 5)


if __name__ == "__main__":
    unittest.main()
