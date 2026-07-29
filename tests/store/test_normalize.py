"""Tests for the normalization adapter over archivum.ingest.parsers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from archivum.ingest.parsers import ParsedDoc
from archivum.store.normalize import NormalizedDoc, normalize


@pytest.mark.asyncio
async def test_normalize_maps_markdown_mime(tmp_path):
    parsed = ParsedDoc(text="# Title\n\nBody", metadata={"type": "md"}, source="x.md")
    with patch(
        "archivum.store.normalize.parse_source",
        new=AsyncMock(return_value=parsed),
    ):
        result = await normalize("file:///x.md")
    assert isinstance(result, NormalizedDoc)
    assert result.text == "# Title\n\nBody"
    assert result.mime == "text/markdown"


@pytest.mark.asyncio
async def test_normalize_unknown_type_falls_back_to_plain():
    parsed = ParsedDoc(text="data", metadata={"type": "weird"}, source="x")
    with patch(
        "archivum.store.normalize.parse_source",
        new=AsyncMock(return_value=parsed),
    ):
        result = await normalize("file:///x")
    assert result.mime == "text/plain"


@pytest.mark.asyncio
async def test_normalize_url_is_html():
    parsed = ParsedDoc(text="page", metadata={"type": "url"}, source="http://x")
    with patch(
        "archivum.store.normalize.parse_source",
        new=AsyncMock(return_value=parsed),
    ):
        result = await normalize("https://example.com")
    assert result.mime == "text/html"
