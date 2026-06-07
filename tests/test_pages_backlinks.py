"""Regression test: GET /{slug}/backlinks must not be shadowed by GET /{slug:path}."""

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class BacklinksRouteTests(unittest.TestCase):
    def setUp(self):
        self.settings = get_settings()
        self.token = create_access_token("owner", "owner", "default", self.settings)
        self.app = create_app()
        self.client = TestClient(self.app)
        self.client.cookies.set("access_token", self.token)

    def test_backlinks_route_not_shadowed_by_slug_catch_all(self):
        """GET /api/pages/my-page/backlinks must return backlinks, not 404."""
        fake_page = {
            "id": 1,
            "slug": "my-page",
            "title": "My Page",
            "content": "",
            "tags": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "authored_by": "owner",
        }
        fake_backlinks = [{"slug": "other-page", "title": "Other Page"}]

        with (
            patch(
                "archivum.api.pages.sqlite.get_page",
                new=AsyncMock(return_value=fake_page),
            ),
            patch(
                "archivum.api.pages.graph.get_backlinks",
                new=AsyncMock(return_value=fake_backlinks),
            ),
        ):
            response = self.client.get("/api/pages/my-page/backlinks")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["slug"], "other-page")

    def test_backlinks_returns_404_when_page_missing(self):
        """Backlinks for a non-existent page should return 404 with page_not_found."""
        with patch(
            "archivum.api.pages.sqlite.get_page",
            new=AsyncMock(return_value=None),
        ):
            response = self.client.get("/api/pages/ghost-page/backlinks")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "page_not_found")

    def test_backlinks_route_parses_slug_without_backlinks_suffix(self):
        """GET /api/pages/compute-blade/backlinks must parse slug as 'compute-blade'."""
        fake_page = {
            "id": 2,
            "slug": "compute-blade",
            "title": "Compute Blade",
            "content": "",
            "tags": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "authored_by": "owner",
        }

        with (
            patch(
                "archivum.api.pages.sqlite.get_page",
                new=AsyncMock(return_value=fake_page),
            ) as mock_get_page,
            patch(
                "archivum.api.pages.graph.get_backlinks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = self.client.get("/api/pages/compute-blade/backlinks")

        self.assertEqual(response.status_code, 200)
        # Verify the slug passed to sqlite was "compute-blade", not "compute-blade/backlinks"
        mock_get_page.assert_called_once_with("compute-blade", "default")

    def test_deeply_nested_slug_backlinks(self):
        """GET /api/pages/hardware/compute-blade/backlinks must parse slug as 'hardware/compute-blade'."""
        fake_page = {
            "id": 3,
            "slug": "hardware/compute-blade",
            "title": "Compute Blade",
            "content": "",
            "tags": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "authored_by": "owner",
        }

        with (
            patch(
                "archivum.api.pages.sqlite.get_page",
                new=AsyncMock(return_value=fake_page),
            ) as mock_get_page,
            patch(
                "archivum.api.pages.graph.get_backlinks",
                new=AsyncMock(return_value=[]),
            ),
        ):
            response = self.client.get("/api/pages/hardware/compute-blade/backlinks")

        self.assertEqual(response.status_code, 200)
        mock_get_page.assert_called_once_with("hardware/compute-blade", "default")


if __name__ == "__main__":
    unittest.main()
