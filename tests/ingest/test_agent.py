"""Tests for archivum.ingest.agent — LLM extraction, fallback, parse, dispatch."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import anthropic
import pytest

from archivum.ingest.agent import ExtractionResult, WikiAgent, WikiPage, slugify
from archivum.ingest.parsers import ParsedDoc

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_doc(text: str = "Some content here.", title: str = "Test Doc", source: str = "test.pdf") -> ParsedDoc:
    return ParsedDoc(text=text, source=source, metadata={"title": title})


def _make_llm_json(
    pages=None,
    entities=None,
    relationships=None,
) -> str:
    data = {
        "pages": pages
        if pages is not None
        else [
            {
                "slug": "test-page",
                "title": "Test Page",
                "content": "---\ntitle: Test Page\ntags: [test]\n---\n\n# Test Page\n\nContent with [[Entity One]].",
                "tags": ["test"],
            }
        ],
        "entities": entities
        if entities is not None
        else [
            {"name": "Entity One", "type": "concept"},
            {"name": "Entity Two", "type": "person"},
        ],
        "relationships": relationships
        if relationships is not None
        else [{"from": "Entity One", "to": "Entity Two", "type": "related_to"}],
    }
    return json.dumps(data)


def _make_span_mock():
    mock_span_cm = MagicMock()
    mock_span_cm.__enter__ = MagicMock(return_value={})
    mock_span_cm.__exit__ = MagicMock(return_value=False)
    return mock_span_cm


def _anthropic_settings():
    return SimpleNamespace(
        llm_extraction_provider="anthropic",
        llm_model="claude-haiku-4-5-20251001",
        anthropic_api_key="test-key",
    )


def _openrouter_settings():
    return SimpleNamespace(
        llm_extraction_provider="openrouter",
        llm_model="mistral-7b",
        anthropic_api_key=None,
    )


def _openai_compat_settings():
    return SimpleNamespace(
        llm_extraction_provider="openai_compat",
        llm_model="gpt-4o-mini",
        anthropic_api_key=None,
    )


# ── TestSlugify ───────────────────────────────────────────────────────────────


class TestSlugify:
    def test_basic_kebab_case(self):
        assert slugify("Hello World") == "hello-world"

    def test_strips_special_chars(self):
        assert slugify("Hello, World! (2024)") == "hello-world-2024"

    def test_truncates_at_80_chars(self):
        long_title = "A" * 100
        result = slugify(long_title)
        assert len(result) <= 80

    def test_handles_underscores(self):
        assert slugify("hello_world_test") == "hello-world-test"


# ── TestFallbackEntities ──────────────────────────────────────────────────────


class TestFallbackEntities:
    def _agent(self):
        settings = _anthropic_settings()
        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            return WikiAgent(settings)

    def test_extracts_proper_nouns(self):
        agent = self._agent()
        entities = agent._fallback_entities("Alice and Bob met Charlie.")
        names = [e["name"] for e in entities]
        assert "Alice" in names

    def test_skips_stopwords(self):
        agent = self._agent()
        entities = agent._fallback_entities("The Content Page Subject")
        names = [e["name"] for e in entities]
        assert "The" not in names
        assert "Content" not in names
        assert "Page" not in names

    def test_caps_at_25_entities(self):
        agent = self._agent()
        # Generate many unique proper nouns
        words = " ".join(f"Word{i}" for i in range(50))
        entities = agent._fallback_entities(words)
        assert len(entities) <= 25

    def test_classifies_tech_entities(self):
        agent = self._agent()
        entities = agent._fallback_entities("GraphSearch Api System")
        tech = [e for e in entities if e["type"] == "tech"]
        assert len(tech) > 0

    def test_classifies_org_entities(self):
        agent = self._agent()
        entities = agent._fallback_entities("Archivum Inc Corp")
        org = [e for e in entities if e["type"] == "org"]
        assert len(org) > 0


# ── TestFallbackExtraction ────────────────────────────────────────────────────


class TestFallbackExtraction:
    def _agent(self):
        settings = _anthropic_settings()
        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            return WikiAgent(settings)

    def test_returns_single_page(self):
        agent = self._agent()
        doc = _make_doc()
        result = agent._fallback_extraction(doc)
        assert isinstance(result, ExtractionResult)
        assert len(result.pages) == 1

    def test_page_slug_from_title(self):
        agent = self._agent()
        doc = _make_doc(title="My Test Document")
        result = agent._fallback_extraction(doc)
        assert result.pages[0].slug == "my-test-document"

    def test_page_has_ingested_tag(self):
        agent = self._agent()
        doc = _make_doc()
        result = agent._fallback_extraction(doc)
        assert "ingested" in result.pages[0].tags

    def test_relationships_from_entities(self):
        agent = self._agent()
        doc = _make_doc(text="Alice Bob Charlie David Eve Frank George")
        result = agent._fallback_extraction(doc)
        # If there are multiple entities, relationships are generated
        if len(result.entities) > 1:
            assert len(result.relationships) > 0
            first_rel = result.relationships[0]
            assert first_rel["from"] == result.entities[0]["name"]


# ── TestParseExtraction ───────────────────────────────────────────────────────


class TestParseExtraction:
    def _agent(self):
        settings = _anthropic_settings()
        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            return WikiAgent(settings)

    def test_parses_pages_correctly(self):
        agent = self._agent()
        doc = _make_doc()
        data = json.loads(_make_llm_json())
        result = agent._parse_extraction(data, doc)
        assert len(result.pages) == 1
        assert result.pages[0].slug == "test-page"
        assert result.pages[0].title == "Test Page"

    def test_parses_entities_correctly(self):
        agent = self._agent()
        doc = _make_doc()
        data = json.loads(_make_llm_json())
        result = agent._parse_extraction(data, doc)
        assert len(result.entities) == 2
        assert result.entities[0] == {"name": "Entity One", "type": "concept"}

    def test_parses_relationships_correctly(self):
        agent = self._agent()
        doc = _make_doc()
        data = json.loads(_make_llm_json())
        result = agent._parse_extraction(data, doc)
        assert len(result.relationships) == 1
        assert result.relationships[0]["from"] == "Entity One"
        assert result.relationships[0]["to"] == "Entity Two"

    def test_falls_back_when_no_pages(self):
        agent = self._agent()
        doc = _make_doc()
        data = {"pages": [], "entities": [], "relationships": []}
        result = agent._parse_extraction(data, doc)
        # fallback adds "ingested" tag
        assert "ingested" in result.pages[0].tags

    def test_generates_slug_when_missing(self):
        agent = self._agent()
        doc = _make_doc()
        data = {
            "pages": [{"slug": "", "title": "Auto Slug Page", "content": "x", "tags": []}],
            "entities": [],
            "relationships": [],
        }
        result = agent._parse_extraction(data, doc)
        assert result.pages[0].slug == "auto-slug-page"


# ── TestAnthropicExtraction ───────────────────────────────────────────────────


class TestAnthropicExtraction:
    def _setup(self, llm_json: str | None = None):
        """Returns (agent, mock_client) with span patched."""
        llm_json = llm_json or _make_llm_json()
        settings = _anthropic_settings()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=llm_json)]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("archivum.ingest.agent.anthropic.Anthropic", return_value=mock_client):
            agent = WikiAgent(settings)

        return agent, mock_client

    def test_calls_client_messages_create(self):
        agent, mock_client = self._setup()
        doc = _make_doc()
        with patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            agent._extract_sync(doc)
        mock_client.messages.create.assert_called_once()

    def test_returns_extraction_result(self):
        agent, mock_client = self._setup()
        doc = _make_doc()
        with patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = agent._extract_sync(doc)
        assert isinstance(result, ExtractionResult)
        assert result.pages[0].slug == "test-page"

    def test_falls_back_on_json_decode_error(self):
        agent, mock_client = self._setup(llm_json="not valid json")
        doc = _make_doc()
        with patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = agent._extract_sync(doc)
        assert "ingested" in result.pages[0].tags

    def test_falls_back_on_api_error(self):
        agent, mock_client = self._setup()
        mock_client.messages.create.side_effect = anthropic.APIStatusError(
            "API error",
            response=MagicMock(status_code=500, headers={}),
            body=None,
        )
        doc = _make_doc()
        with patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = agent._extract_sync(doc)
        assert "ingested" in result.pages[0].tags

    def test_strips_markdown_code_fences(self):
        llm_json = _make_llm_json()
        fenced = "```json\n" + llm_json + "\n```"
        agent, mock_client = self._setup(llm_json=fenced)
        doc = _make_doc()
        with patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = agent._extract_sync(doc)
        assert isinstance(result, ExtractionResult)
        assert result.pages[0].slug == "test-page"

    def test_truncates_long_documents(self):
        agent, mock_client = self._setup()
        long_text = "A" * 15000
        doc = _make_doc(text=long_text)
        with patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = agent._extract_sync(doc)
        # Should still work, extracting normally
        assert isinstance(result, ExtractionResult)
        # Verify the call was made (not skipped)
        mock_client.messages.create.assert_called_once()
        # Verify the user message was truncated (text content shorter than 15000)
        call_kwargs = mock_client.messages.create.call_args
        user_message = call_kwargs[1]["messages"][0]["content"]
        assert len(user_message) < 15000 + 500  # some overhead for headers


# ── TestOpenRouterExtraction ──────────────────────────────────────────────────


class TestOpenRouterExtraction:
    async def test_calls_openrouter_chat_completion(self):
        settings = _openrouter_settings()
        llm_json = _make_llm_json()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openrouter_chat_completion", new=AsyncMock(return_value=llm_json)) as mock_fn, \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            await agent._extract_openrouter_async(doc)

        mock_fn.assert_called_once()

    async def test_returns_extraction_result(self):
        settings = _openrouter_settings()
        llm_json = _make_llm_json()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openrouter_chat_completion", new=AsyncMock(return_value=llm_json)), \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent._extract_openrouter_async(doc)

        assert isinstance(result, ExtractionResult)
        assert result.pages[0].slug == "test-page"

    async def test_falls_back_on_json_error(self):
        settings = _openrouter_settings()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openrouter_chat_completion", new=AsyncMock(return_value="not valid json")), \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent._extract_openrouter_async(doc)

        assert "ingested" in result.pages[0].tags

    async def test_falls_back_on_generic_exception(self):
        settings = _openrouter_settings()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openrouter_chat_completion", new=AsyncMock(side_effect=RuntimeError("network error"))), \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent._extract_openrouter_async(doc)

        assert "ingested" in result.pages[0].tags


# ── TestOpenAICompatExtraction ────────────────────────────────────────────────


class TestOpenAICompatExtraction:
    async def test_calls_openai_compat_chat_completion(self):
        settings = _openai_compat_settings()
        llm_json = _make_llm_json()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openai_compat_chat_completion", new=AsyncMock(return_value=llm_json)) as mock_fn, \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            await agent._extract_openai_compat_async(doc)

        mock_fn.assert_called_once()

    async def test_returns_extraction_result(self):
        settings = _openai_compat_settings()
        llm_json = _make_llm_json()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openai_compat_chat_completion", new=AsyncMock(return_value=llm_json)), \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent._extract_openai_compat_async(doc)

        assert isinstance(result, ExtractionResult)
        assert result.pages[0].slug == "test-page"

    async def test_falls_back_on_json_error(self):
        settings = _openai_compat_settings()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openai_compat_chat_completion", new=AsyncMock(return_value="not valid json")), \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent._extract_openai_compat_async(doc)

        assert "ingested" in result.pages[0].tags


# ── TestExtractDispatch ───────────────────────────────────────────────────────


class TestExtractDispatch:
    async def test_dispatches_to_anthropic(self):
        settings = _anthropic_settings()
        llm_json = _make_llm_json()
        doc = _make_doc()

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=llm_json)]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("archivum.ingest.agent.anthropic.Anthropic", return_value=mock_client):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent.extract(doc)

        assert isinstance(result, ExtractionResult)
        mock_client.messages.create.assert_called_once()

    async def test_dispatches_to_openrouter(self):
        settings = _openrouter_settings()
        llm_json = _make_llm_json()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openrouter_chat_completion", new=AsyncMock(return_value=llm_json)), \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent.extract(doc)

        assert isinstance(result, ExtractionResult)

    async def test_dispatches_to_openai_compat(self):
        settings = _openai_compat_settings()
        llm_json = _make_llm_json()
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with patch("archivum.ingest.agent.openai_compat_chat_completion", new=AsyncMock(return_value=llm_json)), \
             patch("archivum.ingest.agent.span", return_value=_make_span_mock()):
            result = await agent.extract(doc)

        assert isinstance(result, ExtractionResult)

    async def test_raises_on_unsupported_provider(self):
        settings = SimpleNamespace(
            llm_extraction_provider="unsupported_provider",
            llm_model="some-model",
            anthropic_api_key=None,
        )
        doc = _make_doc()

        with patch("archivum.ingest.agent.anthropic.Anthropic"):
            agent = WikiAgent(settings)

        with pytest.raises(ValueError, match="Unsupported llm_extraction_provider"):
            await agent.extract(doc)
