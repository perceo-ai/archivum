from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from archivum.api import context as context_api
from archivum.auth import CurrentUser
from archivum.config import Settings
from archivum.knowledge.models import Citation, ContextPackage, ContextNode
from archivum.main import app
from archivum.retrieval.hybrid import HybridHit


def test_context_package_route_requires_auth_or_test_auth(monkeypatch):
    client = TestClient(app)
    response = client.post("/api/context-package", json={"query": "Alpha", "max_nodes": 5})
    assert response.status_code in {200, 401}


@pytest.mark.asyncio
async def test_context_package_defaults_to_the_authenticated_wiki(monkeypatch):
    package = ContextPackage(
        query="Alpha",
        seeds=["entity:alpha"],
        nodes=[
            ContextNode(
                id="entity:alpha",
                label="Alpha",
                node_type="entity",
                scope="wiki:owner",
                extraction_method="EXTRACTED",
                confidence=0.8,
                citations=[
                    Citation(
                        source_id="page:owner:alpha",
                        chunk_id="page:owner:alpha:chunk:0",
                        span_start=0,
                        span_end=5,
                        quote="Alpha evidence",
                    )
                ],
            )
        ],
        edges=[],
        citations=[],
        insufficient_evidence=False,
        reason=None,
    )

    @asynccontextmanager
    async def fake_db():
        yield object()

    build = AsyncMock(return_value=package)
    monkeypatch.setattr(context_api.sqlite, "get_db", fake_db)
    monkeypatch.setattr(context_api, "build_context_package", build)

    result = await context_api.context_package(
        context_api.ContextPackageRequest(query="Alpha"),
        CurrentUser(username="owner", role="owner", wiki_id="owner"),
    )

    assert result.nodes[0].id == "entity:alpha"
    assert build.await_args.args[1].scope == "wiki:owner"


@pytest.mark.asyncio
async def test_retrieve_returns_compact_cited_hybrid_hits(monkeypatch):
    hit = HybridHit(
        id="entity:alpha",
        label="Alpha",
        score=0.8,
        source="keyword+graph",
        citation=Citation(
            source_id="page:default:alpha",
            chunk_id="page:default:alpha:chunk:0",
            span_start=0,
            span_end=5,
            quote="Alpha evidence",
        ),
    )
    monkeypatch.setattr(context_api, "hybrid_retrieve", AsyncMock(return_value=[hit]))

    result = await context_api.retrieve(
        context_api.RetrieveRequest(query="Alpha"),
        CurrentUser(username="owner", role="owner", wiki_id="default"),
        Settings(),
    )

    assert result.hits[0].id == "entity:alpha"
    assert result.hits[0].label == "Alpha"
    assert result.hits[0].citation == hit.citation
    assert result.hits[0].extraction_method == "EXTRACTED"
    assert result.hits[0].confidence == 0.8
