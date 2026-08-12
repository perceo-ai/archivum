"""Tests for GET /api/search."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from archivum.auth import create_access_token
from archivum.config import get_settings
from archivum.knowledge.models import Citation
from archivum.main import create_app
from archivum.retrieval.hybrid import HybridHit


def _hit(slug: str, *, score: float = 0.9) -> HybridHit:
    page_id = f"page:default:{slug}"
    return HybridHit(
        id=page_id,
        label=slug.title(),
        score=0.04,
        source="keyword+vector",
        citation=Citation(
            source_id=page_id,
            chunk_id=f"{page_id}:chunk:0",
            span_start=None,
            span_end=None,
            quote=f"Evidence for {slug}",
        ),
        raw_score=score,
    )


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

    def test_returns_hybrid_page_results_in_existing_response_shape(self):
        hits = [_hit("alpha"), _hit("beta", score=0.7)]
        with patch("archivum.api.search.hybrid_retrieve", new=AsyncMock(return_value=hits)):
            response = self.client.get("/api/search?q=hello")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            [
                {"slug": "alpha", "title": "Alpha", "excerpt": "Evidence for alpha", "score": 0.9},
                {"slug": "beta", "title": "Beta", "excerpt": "Evidence for beta", "score": 0.7},
            ],
        )

    def test_omits_non_page_graph_hits_and_respects_limit(self):
        graph_hit = HybridHit(
            id="entity:topic",
            label="Topic",
            score=0.02,
            source="graph",
            citation=Citation(
                source_id="source:topic",
                chunk_id="chunk:topic",
                span_start=None,
                span_end=None,
                quote="Graph evidence",
            ),
        )
        with patch(
            "archivum.api.search.hybrid_retrieve",
            new=AsyncMock(return_value=[_hit("alpha"), graph_hit]),
        ) as retrieve:
            response = self.client.get("/api/search?q=topic&limit=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["slug"] for row in response.json()], ["alpha"])
        self.assertEqual(retrieve.await_args.kwargs["limit"], 1)

    def test_requires_auth(self):
        client_no_auth = TestClient(self.app, raise_server_exceptions=True)
        response = client_no_auth.get("/api/search?q=hello")
        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
