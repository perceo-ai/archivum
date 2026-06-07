"""Tests for share endpoints: /api/share/{token} and /api/share-links."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class TestShareView(unittest.TestCase):
    """Public read-only share viewer — no auth required."""

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
        # Public client — no auth cookie needed for /api/share/{token}
        self.public_client = TestClient(self.app, raise_server_exceptions=True)

    def test_get_share_page_returns_page_data(self):
        """GET /api/share/{token} with a page link returns the shared page data."""
        valid_token = "validtoken1234567890"
        fake_link = {
            "id": 1,
            "wiki_id": "default",
            "token": valid_token,
            "type": "page",
            "target_id": "shared-page",
            "created_at": "2026-01-01T00:00:00",
            "expires_at": None,
            "revoked": 0,
        }
        fake_page = {
            "slug": "shared-page",
            "title": "Shared Page",
            "content": "This is the shared content.",
            "tags": "[]",
        }
        with (
            patch("archivum.api.share.sqlite.get_share_link", new=AsyncMock(return_value=fake_link)),
            patch("archivum.api.share.sqlite.get_page", new=AsyncMock(return_value=fake_page)),
        ):
            response = self.public_client.get(f"/api/share/{valid_token}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["type"], "page")
        self.assertEqual(data["slug"], "shared-page")
        self.assertEqual(data["title"], "Shared Page")
        self.assertEqual(data["token"], valid_token)

    def test_get_share_returns_404_for_invalid_token(self):
        """GET /api/share/{token} returns 404 when the share link does not exist."""
        valid_token = "validtoken1234567890"
        with patch("archivum.api.share.sqlite.get_share_link", new=AsyncMock(return_value=None)):
            response = self.public_client.get(f"/api/share/{valid_token}")

        self.assertEqual(response.status_code, 404)


class TestShareLinkManagement(unittest.TestCase):
    """Authenticated share-link management: create, list, revoke."""

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
        # Use Bearer auth so POST/DELETE bypass CSRF middleware
        self.client = TestClient(self.app, raise_server_exceptions=True)
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    def test_create_share_link(self):
        """POST /api/share-links creates a new share link and returns token + url."""
        fake_page = {
            "slug": "my-page",
            "title": "My Page",
            "content": "Hello world",
            "tags": "[]",
        }
        with (
            patch("archivum.api.share.sqlite.get_page", new=AsyncMock(return_value=fake_page)),
            patch("archivum.api.share.sqlite.create_share_link", new=AsyncMock()),
        ):
            response = self.client.post(
                "/api/share-links",
                json={"type": "page", "target_id": "my-page"},
            )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("token", data)
        self.assertIn("url", data)
        self.assertTrue(data["url"].startswith("/share/"))

    def test_list_share_links(self):
        """GET /api/share-links returns all share links for the wiki."""
        fake_links = [
            {
                "id": 1,
                "wiki_id": "default",
                "token": "abc123defgh",
                "type": "page",
                "target_id": "some-page",
                "created_at": "2026-01-01T00:00:00",
                "expires_at": None,
                "revoked": 0,
            }
        ]
        with patch("archivum.api.share.sqlite.list_share_links", new=AsyncMock(return_value=fake_links)):
            response = self.client.get("/api/share-links")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["token"], "abc123defgh")

    def test_revoke_share_link(self):
        """DELETE /api/share-links/{token} revokes the share link."""
        token_val = "abc123defghijk"
        with patch("archivum.api.share.sqlite.revoke_share_link", new=AsyncMock(return_value=True)):
            response = self.client.delete(f"/api/share-links/{token_val}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["detail"], "revoked")


if __name__ == "__main__":
    unittest.main()
