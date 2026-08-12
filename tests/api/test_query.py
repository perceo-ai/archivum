"""Tests for cited hybrid query answers."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from archivum.api import query as query_api
from archivum.auth import CurrentUser
from archivum.config import Settings
from archivum.knowledge.models import Citation, ContextNode, ContextPackage
from archivum.retrieval.hybrid import HybridHit


def _hit() -> HybridHit:
    return HybridHit(
        id="entity:alpha",
        label="Alpha",
        score=0.04,
        source="graph",
        citation=Citation(
            source_id="source:alpha",
            chunk_id="chunk:alpha",
            span_start=0,
            span_end=8,
            quote="Alpha evidence",
        ),
    )


async def _events(response):
    return [event async for event in response.body_iterator]


@pytest.mark.asyncio
async def test_query_returns_insufficient_evidence_when_synthesis_omits_citation():
    async def uncited_tokens(**kwargs):
        yield "Alpha is relevant."

    with (
        patch("archivum.api.query.hybrid_retrieve", new=AsyncMock(return_value=[_hit()])),
        patch("archivum.api.query._scope_hits_to_context_package", new=AsyncMock(return_value=[_hit()])),
        patch("archivum.api.query.sqlite.get_pages", new=AsyncMock(return_value=[])),
        patch("archivum.api.query.openai_compat_stream_tokens", uncited_tokens),
    ):
        response = await query_api.query(
            query_api.QueryRequest(question="What is Alpha?"),
            CurrentUser(username="owner", role="owner", wiki_id="default"),
            Settings(llm_synthesis_provider="ollama"),
        )
        events = await _events(response)

    payloads = [json.loads(event["data"]) for event in events if event["data"] != "[DONE]"]
    assert payloads[0]["citations"][0]["citation"]["source_id"] == "source:alpha"
    assert payloads[1]["token"].startswith("Insufficient evidence")


@pytest.mark.asyncio
async def test_query_returns_insufficient_evidence_without_usable_context():
    async def should_not_run(**kwargs):
        raise AssertionError("synthesis should not run without evidence")

    hit = _hit()
    uncited_hit = replace(hit, citation=hit.citation.model_copy(update={"quote": None}))
    with (
        patch("archivum.api.query.hybrid_retrieve", new=AsyncMock(return_value=[uncited_hit])),
        patch("archivum.api.query._scope_hits_to_context_package", new=AsyncMock(return_value=[uncited_hit])),
        patch("archivum.api.query.sqlite.get_pages", new=AsyncMock(return_value=[])),
        patch("archivum.api.query.openai_compat_stream_tokens", should_not_run),
    ):
        response = await query_api.query(
            query_api.QueryRequest(question="What is missing?"),
            CurrentUser(username="owner", role="owner", wiki_id="default"),
            Settings(llm_synthesis_provider="ollama"),
        )
        events = await _events(response)

    payloads = [json.loads(event["data"]) for event in events if event["data"] != "[DONE]"]
    assert payloads[0]["citations"] == []
    assert payloads[1]["token"].startswith("Insufficient evidence")
    assert events[-1]["data"] == "[DONE]"


@pytest.mark.asyncio
async def test_query_scopes_hybrid_hits_through_a_context_package(monkeypatch):
    first_hit = _hit()
    second_hit = replace(first_hit, id="entity:beta", label="Beta")
    hits = [first_hit, second_hit]
    package = ContextPackage(
        query="Alpha",
        seeds=["entity:alpha"],
        nodes=[
            ContextNode(
                id="entity:alpha",
                label="Alpha",
                node_type="entity",
                scope="wiki:default",
                citations=[first_hit.citation],
            )
        ],
        edges=[],
        citations=[first_hit.citation],
        insufficient_evidence=False,
        reason=None,
    )

    class FakeDatabase:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    build = AsyncMock(return_value=package)
    monkeypatch.setattr(query_api.sqlite, "get_db", FakeDatabase)
    monkeypatch.setattr(query_api, "build_context_package", build)

    scoped = await query_api._scope_hits_to_context_package("Alpha", "default", hits)

    assert scoped == [first_hit]
    request = build.await_args.args[1]
    assert request.scope == "wiki:default"
    assert request.seed_ids == ["entity:alpha", "entity:beta"]


@pytest.mark.asyncio
async def test_query_scope_filter_does_not_fallback_to_unscoped_hits(monkeypatch):
    hit = _hit()
    package = ContextPackage(
        query="Unrelated",
        seeds=["person:self"],
        nodes=[
            ContextNode(
                id="person:self",
                label="Me",
                node_type="person",
                scope="person:self",
                citations=[Citation(source_id="person:self", chunk_id="person:self", span_start=None, span_end=None, quote="Me")],
            )
        ],
        edges=[],
        citations=[],
        insufficient_evidence=True,
        reason="No cited knowledge objects matched the requested context.",
    )

    class FakeDatabase:
        async def __aenter__(self):
            return object()

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    monkeypatch.setattr(query_api.sqlite, "get_db", FakeDatabase)
    monkeypatch.setattr(query_api, "build_context_package", AsyncMock(return_value=package))

    scoped = await query_api._scope_hits_to_context_package("Unrelated", "default", [hit])

    assert scoped == []
