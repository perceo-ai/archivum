"""Tests for GET /api/export."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


class TestExportEndpoint(unittest.TestCase):
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

    def _fake_page(self, slug="my-page", title="My Page", content="# Hello\n\nWorld."):
        return {
            "slug": slug,
            "title": title,
            "content": content,
            "tags": [],
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "authored_by": "owner",
        }

    def test_export_html_returns_html_response(self):
        """GET /api/export?slug=...&format=html returns HTML content."""
        fake_page = self._fake_page()
        with patch("archivum.api.export.sqlite.get_page", new=AsyncMock(return_value=fake_page)):
            response = self.client.get("/api/export?slug=my-page&format=html")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn(b"<!DOCTYPE html>", response.content)
        self.assertIn(b"My Page", response.content)
        self.assertIn("attachment", response.headers.get("content-disposition", ""))

    def test_export_markdown_returns_content_as_markdown(self):
        """GET /api/export?slug=...&format=html includes the markdown content rendered as HTML."""
        fake_page = self._fake_page(content="# Header\n\nSome **bold** text.")
        with patch("archivum.api.export.sqlite.get_page", new=AsyncMock(return_value=fake_page)):
            response = self.client.get("/api/export?slug=my-page&format=html")

        self.assertEqual(response.status_code, 200)
        # The markdown content should be rendered into HTML
        self.assertIn(b"<strong>bold</strong>", response.content)

    def test_export_pdf_smoke(self):
        """GET /api/export?slug=...&format=pdf returns PDF bytes when weasyprint is mocked."""
        fake_page = self._fake_page()
        mock_pdf = b"%PDF-1.4 fake pdf bytes"

        mock_html_instance = MagicMock()
        mock_html_instance.write_pdf.return_value = mock_pdf
        mock_weasyprint_html_cls = MagicMock(return_value=mock_html_instance)

        # Patch the local import inside the endpoint so it always resolves,
        # regardless of whether system libraries for weasyprint are available.
        import sys
        mock_weasyprint_module = MagicMock()
        mock_weasyprint_module.HTML = mock_weasyprint_html_cls

        with (
            patch("archivum.api.export.sqlite.get_page", new=AsyncMock(return_value=fake_page)),
            patch.dict(sys.modules, {"weasyprint": mock_weasyprint_module}),
        ):
            response = self.client.get("/api/export?slug=my-page&format=pdf")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.content, mock_pdf)

    def test_export_returns_404_when_page_missing(self):
        """GET /api/export returns 404 when the slug does not exist."""
        with patch("archivum.api.export.sqlite.get_page", new=AsyncMock(return_value=None)):
            response = self.client.get("/api/export?slug=nonexistent&format=html")

        self.assertEqual(response.status_code, 404)

    def test_export_requires_auth(self):
        """Requests without a token should return 401."""
        client_no_auth = TestClient(self.app, raise_server_exceptions=True)
        with patch("archivum.api.export.sqlite.get_page", new=AsyncMock(return_value=self._fake_page())):
            response = client_no_auth.get("/api/export?slug=my-page&format=html")

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
