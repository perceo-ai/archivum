"""Tests for first-class wiki folders and page move routes."""

from __future__ import annotations

import contextlib
import unittest
from unittest.mock import AsyncMock, patch

import pytest_asyncio
from fastapi.testclient import TestClient

import archivum.db.sqlite as sqlite_mod
from archivum.api.folders import delete_folder_tree
from archivum.auth import create_access_token
from archivum.config import Settings, get_settings
from archivum.indexing import reindex_page
from archivum.knowledge.repository import KnowledgeRepository
from archivum.knowledge.suggestions import (
    SuggestionRepository,
    init_suggestion_schema,
    wiki_scope,
)
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


# ── Deleting a folder must forget its pages everywhere ────────────────────────
#
# These run against a real SQLite file rather than mocking the function under
# test, because the defect they cover was precisely that folder delete had its
# own hand-rolled fan-out and skipped stores the single-page path cleans up.


@pytest_asyncio.fixture
async def vault(tmp_path):
    settings = Settings(
        db_path=tmp_path / "archivum.db",
        blob_dir=tmp_path / "blobs",
        wiki_dir=tmp_path / "wiki",
    )
    await sqlite_mod.init_db(settings)
    settings.wiki_dir.mkdir(parents=True, exist_ok=True)
    return settings


async def _page_in_folder(settings, folder: str, slug: str, title: str) -> None:
    path = settings.wiki_dir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\n\n# {title}\n", encoding="utf-8")
    await sqlite_mod.create_folder(folder, "default")
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.graph.clear_references_from_page", new=AsyncMock()),
        patch("archivum.indexing.graph.add_reference", new=AsyncMock()),
    ):
        await reindex_page(
            slug, wiki_id="default", settings=settings, force=True, distill=False
        )


@contextlib.contextmanager
def _folder_projections_offline():
    """Stand in for the rebuildable stores, so the test covers the canonical half."""
    with (
        patch("archivum.indexing.qdrant.delete_page", new=AsyncMock()),
        patch("archivum.indexing.graph.delete_page_node", new=AsyncMock()),
        patch("archivum.indexing.graph.cleanup_abandoned_nodes", new=AsyncMock()),
    ):
        yield


async def test_deleting_a_folder_removes_its_pages_from_canonical_knowledge(vault, mock_kuzu_conn):
    await _page_in_folder(vault, "projects", "projects/alpha", "Alpha")

    with _folder_projections_offline():
        await delete_folder_tree("projects", True, "default", vault)

    async with sqlite_mod.get_db() as conn:
        assert await KnowledgeRepository(conn).get_object("page:default:projects/alpha") is None


async def test_deleting_a_folder_retires_review_items_for_its_pages(vault, mock_kuzu_conn):
    await _page_in_folder(vault, "projects", "projects/alpha", "Alpha")
    async with sqlite_mod.get_db() as conn:
        await init_suggestion_schema(conn)
        await SuggestionRepository(conn).create_suggestion(
            target_id="page:default:projects/alpha",
            suggestion_type="memory_atom",
            proposed_markdown="Alpha ships in March.",
            proposed_objects=[],
            citations=[],
        )

    with _folder_projections_offline():
        await delete_folder_tree("projects", True, "default", vault)

    async with sqlite_mod.get_db() as conn:
        pending = await SuggestionRepository(conn).list_suggestions(
            status="pending", **wiki_scope("default")
        )
    assert pending == []


# ── Moving a page keeps the references other pages make to it by title ──────


@contextlib.contextmanager
def _move_projections_offline():
    with (
        patch("archivum.indexing.qdrant.upsert_page", new=AsyncMock()),
        patch("archivum.indexing.qdrant.delete_page", new=AsyncMock()),
        patch("archivum.api.pages.qdrant.delete_page", new=AsyncMock()),
        patch("archivum.api.folders.qdrant.delete_page", new=AsyncMock()),
    ):
        yield


async def _title_references_to(slug: str) -> dict[str, str]:
    async with sqlite_mod.get_db() as conn:
        rels = await KnowledgeRepository(conn).list_relationships(scope="wiki:default")
    return {
        rel.src_id: rel.extraction_method
        for rel in rels
        if rel.rel_type == "references" and rel.dst_id == f"page:default:{slug}"
    }


async def _notes_naming_archfleet(settings) -> None:
    path = settings.wiki_dir / "notes.md"
    path.write_text("# Notes\n\nArchfleet runs the VMs.\n", encoding="utf-8")
    with _move_projections_offline():
        await reindex_page("notes", wiki_id="default", settings=settings, distill=False)


async def test_moving_a_page_keeps_the_pages_that_name_it_linked(vault, mock_kuzu_conn):
    """A move replaces the page's record, and with it every edge into it.

    The title did not change, so nothing re-read the notes that name it; they
    lost their path to the page until someone edited them.
    """
    from archivum.api.pages import move_page_to_slug

    await _page_in_folder(vault, "projects", "projects/archfleet", "Archfleet")
    await _notes_naming_archfleet(vault)
    assert await _title_references_to("projects/archfleet") == {"page:default:notes": "INFERRED"}

    with _move_projections_offline():
        await move_page_to_slug("projects/archfleet", "archive/archfleet", "default", vault)

    assert await _title_references_to("archive/archfleet") == {"page:default:notes": "INFERRED"}


async def test_moving_a_folder_keeps_the_pages_that_name_its_pages_linked(vault, mock_kuzu_conn):
    """And the record left at the old slug must go, or it keeps the title."""
    from archivum.api.folders import move_folder_tree

    await _page_in_folder(vault, "projects", "projects/archfleet", "Archfleet")
    await _notes_naming_archfleet(vault)

    with _move_projections_offline():
        await move_folder_tree("projects", "archive", True, "default", vault)

    async with sqlite_mod.get_db() as conn:
        assert await KnowledgeRepository(conn).get_object("page:default:projects/archfleet") is None
    assert await _title_references_to("archive/archfleet") == {"page:default:notes": "INFERRED"}
