"""Tests for first-class wiki folders and page move routes."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class FolderRouteTests(unittest.TestCase):
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
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    def test_list_folders_returns_wiki_scoped_folders(self):
        folders = [
            {
                "path": "projects",
                "name": "projects",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
            }
        ]
        with patch("archivum.api.folders.sqlite.list_folders", new=AsyncMock(return_value=folders)):
            response = self.client.get("/api/folders")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), folders)

    def test_create_folder_rejects_page_slug_collision(self):
        with (
            patch("archivum.api.folders.sqlite.get_page", new=AsyncMock(return_value={"slug": "projects"})),
            patch("archivum.api.folders.sqlite.get_folder", new=AsyncMock(return_value=None)),
        ):
            response = self.client.post("/api/folders", json={"path": "projects"})

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "path_collision")

    def test_move_folder_returns_affected_counts(self):
        result = {"path": "archive/projects", "pages": 2, "folders": 1}
        with patch("archivum.api.folders.move_folder_tree", new=AsyncMock(return_value=result)):
            response = self.client.patch(
                "/api/folders/projects",
                json={"new_path": "archive/projects", "recursive": True},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)


class PageMoveRouteTests(unittest.TestCase):
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
        self.client.headers.update({"Authorization": f"Bearer {self.token}"})

    def test_move_page_route_moves_to_new_slug(self):
        moved = {
            "id": 1,
            "slug": "archive/note",
            "title": "Note",
            "content": "# Note",
            "tags": "[]",
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "authored_by": "user",
        }
        with patch("archivum.api.pages.move_page_to_slug", new=AsyncMock(return_value=moved)):
            response = self.client.patch(
                "/api/pages/projects/note/move",
                json={"new_slug": "archive/note"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["slug"], "archive/note")


if __name__ == "__main__":
    unittest.main()
