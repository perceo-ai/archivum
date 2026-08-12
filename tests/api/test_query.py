"""Tests for cited hybrid query answers."""

from __future__ import annotations

import json
from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest

from archivum.api import query as query_api
from archivum.auth import CurrentUser
from archivum.config import Settings
from archivum.knowledge.models import Citation
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
async def test_query_appends_a_valid_citation_when_synthesis_omits_one():
    async def uncited_tokens(**kwargs):
        yield "Alpha is relevant."

    with (
        patch("archivum.api.query.hybrid_retrieve", new=AsyncMock(return_value=[_hit()])),
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
    assert payloads[1] == {"type": "token", "token": "Alpha is relevant. [1]"}


@pytest.mark.asyncio
async def test_query_returns_insufficient_evidence_without_usable_context():
    async def should_not_run(**kwargs):
        raise AssertionError("synthesis should not run without evidence")

    hit = _hit()
    uncited_hit = replace(hit, citation=hit.citation.model_copy(update={"quote": None}))
    with (
        patch("archivum.api.query.hybrid_retrieve", new=AsyncMock(return_value=[uncited_hit])),
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
