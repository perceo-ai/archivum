"""Tests for system endpoints: /api/audio-support, /api/rebuild-indexes, /api/lint, /api/lint/fix."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.main import create_app


def _make_client(app, token: str, *, bearer: bool = False) -> TestClient:
    client = TestClient(app, raise_server_exceptions=True)
    if bearer:
        # Bearer auth bypasses CSRF middleware (needed for mutating endpoints)
        client.headers.update({"Authorization": f"Bearer {token}"})
    else:
        client.cookies.set("access_token", token)
    return client


class TestAudioSupport(unittest.TestCase):
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
        self.client = _make_client(self.app, self.token)

    def test_returns_audio_support_status(self):
        """GET /api/audio-support returns availability dict."""
        response = self.client.get("/api/audio-support")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("available", data)
        self.assertIn("dependencies", data)
        self.assertIsInstance(data["available"], bool)


class TestRebuildIndexes(unittest.TestCase):
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
        # Use bearer token to bypass CSRF for POST
        self.client = _make_client(self.app, self.token, bearer=True)

    def _fake_pages(self):
        return [
            {"slug": "page-one", "title": "Page One", "content": "Hello [[page-two]]"},
            {"slug": "page-two", "title": "Page Two", "content": ""},
        ]

    def test_smoke_rebuild_indexes(self):
        """POST /api/rebuild-indexes completes without error."""
        fake_pages = self._fake_pages()
        with (
            patch("archivum.api.system.sqlite.list_pages", new=AsyncMock(return_value=fake_pages)),
            patch("archivum.api.system.qdrant.init_collection", new=AsyncMock()),
            patch("archivum.api.system.graph.init_graph", new=AsyncMock()),
            patch("archivum.api.system.qdrant.upsert_page", new=AsyncMock()),
            patch("archivum.api.system.graph.upsert_page", new=AsyncMock()),
            patch("archivum.api.system.graph.add_reference", new=AsyncMock()),
            patch(
                "archivum.api.system.sqlite.get_page",
                new=AsyncMock(return_value={"slug": "page-two", "title": "Page Two"}),
            ),
        ):
            response = self.client.post("/api/rebuild-indexes")

        self.assertEqual(response.status_code, 200)

    def test_rebuild_returns_page_count(self):
        """POST /api/rebuild-indexes response includes page count."""
        fake_pages = self._fake_pages()
        with (
            patch("archivum.api.system.sqlite.list_pages", new=AsyncMock(return_value=fake_pages)),
            patch("archivum.api.system.qdrant.init_collection", new=AsyncMock()),
            patch("archivum.api.system.graph.init_graph", new=AsyncMock()),
            patch("archivum.api.system.qdrant.upsert_page", new=AsyncMock()),
            patch("archivum.api.system.graph.upsert_page", new=AsyncMock()),
            patch("archivum.api.system.graph.add_reference", new=AsyncMock()),
            patch("archivum.api.system.sqlite.get_page", new=AsyncMock(return_value=None)),
        ):
            response = self.client.post("/api/rebuild-indexes")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["pages"], 2)
        self.assertIn("detail", data)


class TestLintWiki(unittest.TestCase):
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
        self.client = _make_client(self.app, self.token)

    def test_lint_returns_empty_when_no_issues(self):
        """GET /api/lint returns no issues for clean pages."""
        clean_pages = [
            {"slug": "a", "content": "[[b]]"},
            {"slug": "b", "content": "[[a]]"},
        ]
        with patch("archivum.api.system.sqlite.list_pages", new=AsyncMock(return_value=clean_pages)):
            response = self.client.get("/api/lint")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["counts"]["issues"], 0)
        self.assertEqual(len(data["issues"]), 0)

    def test_lint_detects_broken_wikilinks(self):
        """GET /api/lint reports broken_wikilink when target page does not exist."""
        pages = [
            {"slug": "has-broken", "content": "See [[missing-page]] for details."},
        ]
        with patch("archivum.api.system.sqlite.list_pages", new=AsyncMock(return_value=pages)):
            response = self.client.get("/api/lint")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        broken = [i for i in data["issues"] if i["type"] == "broken_wikilink"]
        self.assertGreater(len(broken), 0)
        self.assertEqual(broken[0]["target"], "missing-page")
        self.assertEqual(broken[0]["page"], "has-broken")

    def test_lint_detects_orphan_pages(self):
        """GET /api/lint reports orphan_page for pages with no links in or out."""
        pages = [
            {"slug": "island", "content": "No links here."},
        ]
        with patch("archivum.api.system.sqlite.list_pages", new=AsyncMock(return_value=pages)):
            response = self.client.get("/api/lint")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        orphans = [i for i in data["issues"] if i["type"] == "orphan_page"]
        self.assertGreater(len(orphans), 0)
        self.assertEqual(orphans[0]["page"], "island")

    def test_lint_detects_contradictory_boolean_claims(self):
        """GET /api/lint reports contradictory_claim for enabled/disabled statements."""
        pages = [
            {"slug": "ops-a", "content": "Public wiki is enabled."},
            {"slug": "ops-b", "content": "Public wiki is disabled."},
        ]
        with patch("archivum.api.system.sqlite.list_pages", new=AsyncMock(return_value=pages)):
            response = self.client.get("/api/lint")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        contradictions = [i for i in data["issues"] if i["type"] == "contradictory_claim"]
        self.assertEqual(len(contradictions), 1)
        self.assertEqual(contradictions[0]["subject"], "public wiki")
        self.assertEqual(contradictions[0]["pages"], ["ops-a", "ops-b"])


class TestLintFix(unittest.TestCase):
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
        # Bearer token for POST (bypasses CSRF)
        self.client = _make_client(self.app, self.token, bearer=True)

    def test_fix_broken_wikilink(self):
        """POST /api/lint/fix with type=broken_wikilink patches the page content."""
        fake_page = {
            "slug": "source-page",
            "title": "Source",
            "content": "See [[dead-link]] for info.",
            "tags": "[]",
            "authored_by": "owner",
        }
        with (
            patch("archivum.api.system.sqlite.get_page", new=AsyncMock(return_value=fake_page)),
            patch("archivum.api.system.sqlite.upsert_page", new=AsyncMock()) as mock_upsert,
        ):
            response = self.client.post(
                "/api/lint/fix",
                json={"type": "broken_wikilink", "source_slug": "source-page", "link_target": "dead-link"},
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["detail"], "fixed")
        mock_upsert.assert_called_once()
        # Content passed to upsert_page should no longer contain the wikilink
        call_kwargs = mock_upsert.call_args.kwargs
        self.assertNotIn("[[dead-link]]", call_kwargs.get("content", ""))

    def test_fix_orphan_returns_no_auto_fix(self):
        """POST /api/lint/fix with type=orphan returns no_auto_fix detail."""
        response = self.client.post(
            "/api/lint/fix",
            json={"type": "orphan", "slug": "lonely-page"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["detail"], "no_auto_fix")

    def test_fix_broken_wikilink_returns_404_when_page_not_found(self):
        """POST /api/lint/fix returns 404 if source_slug page does not exist."""
        with patch("archivum.api.system.sqlite.get_page", new=AsyncMock(return_value=None)):
            response = self.client.post(
                "/api/lint/fix",
                json={"type": "broken_wikilink", "source_slug": "ghost-page", "link_target": "dead-link"},
            )

        self.assertEqual(response.status_code, 404)

    def test_fix_unknown_type_returns_400(self):
        """POST /api/lint/fix with an unrecognised type returns 400."""
        response = self.client.post(
            "/api/lint/fix",
            json={"type": "unknown_type", "source_slug": "some-page"},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
