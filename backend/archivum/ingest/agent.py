"""LLM wiki agent: extract entities, generate wiki pages, build graph structure.

Uses claude-haiku with prompt caching on the system prompt.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import anthropic

from archivum.config import Settings, get_settings
from archivum.ingest.parsers import ParsedDoc
from archivum.llm.openrouter_client import openrouter_chat_completion
from archivum.llm.openai_compat_client import openai_compat_chat_completion
from archivum.observability import span

logger = logging.getLogger(__name__)

# ── System prompt (cached) ────────────────────────────────────────────────────

WIKI_SYSTEM_PROMPT = """\
You are a wiki agent that extracts structured knowledge from documents and writes \
clean Markdown wiki pages.

Given a document, you must:
1. Identify the main topic and write a comprehensive wiki page for it
2. Extract named entities (people, concepts, organizations, technologies, places)
3. Identify relationships between entities
4. Write factual, encyclopedic content — no meta-commentary
5. Add frontmatter with: title, tags, entities, source_url (if available)
6. Use [[wikilink]] syntax to link to related concepts you mention
7. If the document is very long or complex, split it into multiple focused pages

Return ONLY valid JSON in this exact structure (no markdown code fences, no extra text):
{
  "pages": [
    {
      "slug": "kebab-case-slug",
      "title": "Page Title",
      "content": "---\\ntitle: Page Title\\ntags: [tag1, tag2]\\nentities: [Entity1, Entity2]\\nsource_url: https://...\\n---\\n\\n# Page Title\\n\\nContent here with [[wikilinks]] to related concepts.",
      "tags": ["tag1", "tag2"]
    }
  ],
  "entities": [
    {"name": "Entity Name", "type": "person|concept|org|place|tech"}
  ],
  "relationships": [
    {"from": "entity_name", "to": "entity_name", "type": "related_to|mentioned_with|contrasts"}
  ]
}

Rules:
- slug must be kebab-case (lowercase, hyphens only, no special chars)
- content must be valid Markdown with YAML frontmatter
- Use [[Entity Name]] wikilink syntax for all named entities
- Be factual and concise — no phrases like "this document discusses" or "the text mentions"
- If source has a URL, include it in frontmatter as source_url
"""


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class WikiPage:
    slug: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    pages: list[WikiPage]
    entities: list[dict[str, str]]       # {name, type}
    relationships: list[dict[str, str]]  # {from, to, type}


# ── Slug utilities ────────────────────────────────────────────────────────────

def slugify(title: str) -> str:
    """Convert a title to a kebab-case slug."""
    slug = title.lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:80]


# ── Agent ─────────────────────────────────────────────────────────────────────

class WikiAgent:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = (
            anthropic.Anthropic(api_key=self.settings.anthropic_api_key)
            if self.settings.llm_extraction_provider == "anthropic"
            else None
        )

    async def extract(self, doc: ParsedDoc) -> ExtractionResult:
        """Extract structured wiki data from a ParsedDoc.

        Uses prompt caching on the system prompt. Sends up to 4000 chars of doc text
        to keep token costs low.
        """
        if self.settings.llm_extraction_provider == "anthropic":
            import asyncio

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._extract_sync, doc)

        if self.settings.llm_extraction_provider == "openrouter":
            return await self._extract_openrouter_async(doc)

        if self.settings.llm_extraction_provider in {"openai_compat", "ollama"}:
            return await self._extract_openai_compat_async(doc)

        raise ValueError(f"Unsupported llm_extraction_provider: {self.settings.llm_extraction_provider}")

    def _extract_sync(self, doc: ParsedDoc) -> ExtractionResult:
        # Truncate very long documents
        text = doc.text
        if len(text) > 12000:
            text = text[:12000] + "\n\n[... document truncated for processing ...]"

        source_hint = ""
        if doc.source:
            source_hint = f"\nSource: {doc.source}"
        if doc.metadata.get("url"):
            source_hint = f"\nSource URL: {doc.metadata['url']}"
        if doc.metadata.get("title"):
            source_hint += f"\nDocument title: {doc.metadata['title']}"

        user_message = f"Extract and structure the following document into wiki pages:{source_hint}\n\n---\n\n{text}"

        try:
            with span("anthropic.extract_sync", model=self.settings.llm_model) as sp:
                logger.info(
                    "Anthropic extraction start",
                    extra={"model": self.settings.llm_model, "doc_chars": len(doc.text or ""), "sent_chars": len(text), **sp},
                )
            assert self._client is not None  # for mypy/type checkers
            response = self._client.messages.create(
                model=self.settings.llm_model,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": WIKI_SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": user_message}],
            )

            raw_json = response.content[0].text.strip()

            # Strip accidental markdown code fences
            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json)
                raw_json = re.sub(r"\s*```$", "", raw_json)

            data = json.loads(raw_json)
            logger.info(
                "Anthropic extraction done",
                extra={"model": self.settings.llm_model, "raw_json_chars": len(raw_json or ""), **sp},
            )
            return self._parse_extraction(data, doc)

        except json.JSONDecodeError as exc:
            logger.error("Agent returned invalid JSON: %s", exc)
            return self._fallback_extraction(doc)
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            return self._fallback_extraction(doc)

    async def _extract_openrouter_async(self, doc: ParsedDoc) -> ExtractionResult:
        """OpenRouter-backed extraction (entities + relationships)."""
        # Truncate very long documents (same policy as Anthropic path).
        text = doc.text
        if len(text) > 12000:
            text = text[:12000] + "\n\n[... document truncated for processing ...]"

        source_hint = ""
        if doc.source:
            source_hint = f"\nSource: {doc.source}"
        if doc.metadata.get("url"):
            source_hint = f"\nSource URL: {doc.metadata['url']}"
        if doc.metadata.get("title"):
            source_hint += f"\nDocument title: {doc.metadata['title']}"

        user_message = f"Extract and structure the following document into wiki pages:{source_hint}\n\n---\n\n{text}"

        try:
            with span("openrouter.extract", model=self.settings.llm_model) as sp:
                logger.info(
                    "OpenRouter extraction start",
                    extra={"model": self.settings.llm_model, "doc_chars": len(doc.text or ""), "sent_chars": len(text), **sp},
                )
                raw = await openrouter_chat_completion(
                    settings=self.settings,
                    model=self.settings.llm_model,
                    max_tokens=4096,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": WIKI_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                )

            raw_json = raw.strip()

            # Strip accidental markdown code fences
            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json)
                raw_json = re.sub(r"\s*```$", "", raw_json)

            data = json.loads(raw_json)
            logger.info(
                "OpenRouter extraction done",
                extra={"model": self.settings.llm_model, "raw_json_chars": len(raw_json or ""), **sp},
            )
            return self._parse_extraction(data, doc)
        except json.JSONDecodeError as exc:
            logger.error("OpenRouter returned invalid JSON: %s", exc)
            return self._fallback_extraction(doc)
        except Exception as exc:
            logger.error("OpenRouter extraction error: %s", exc)
            return self._fallback_extraction(doc)

    async def _extract_openai_compat_async(self, doc: ParsedDoc) -> ExtractionResult:
        """OpenAI-compatible extraction (includes OpenAI, Together, Fireworks, Ollama, etc.)."""
        text = doc.text
        if len(text) > 12000:
            text = text[:12000] + "\n\n[... document truncated for processing ...]"

        source_hint = ""
        if doc.source:
            source_hint = f"\nSource: {doc.source}"
        if doc.metadata.get("url"):
            source_hint = f"\nSource URL: {doc.metadata['url']}"
        if doc.metadata.get("title"):
            source_hint += f"\nDocument title: {doc.metadata['title']}"

        user_message = f"Extract and structure the following document into wiki pages:{source_hint}\n\n---\n\n{text}"

        try:
            provider = self.settings.llm_extraction_provider
            with span("openai_compat.extract", provider=provider, model=self.settings.llm_model) as sp:
                logger.info(
                    "OpenAI-compatible extraction start",
                    extra={"provider": provider, "model": self.settings.llm_model, "doc_chars": len(doc.text or ""), "sent_chars": len(text), **sp},
                )
                raw = await openai_compat_chat_completion(
                    settings=self.settings,
                    provider=provider,
                    model=self.settings.llm_model,
                    max_tokens=4096,
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": WIKI_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                )

            raw_json = raw.strip()
            if raw_json.startswith("```"):
                raw_json = re.sub(r"^```(?:json)?\s*", "", raw_json)
                raw_json = re.sub(r"\s*```$", "", raw_json)

            data = json.loads(raw_json)
            logger.info(
                "OpenAI-compatible extraction done",
                extra={"provider": provider, "model": self.settings.llm_model, "raw_json_chars": len(raw_json or ""), **sp},
            )
            return self._parse_extraction(data, doc)
        except json.JSONDecodeError as exc:
            logger.error("OpenAI-compatible provider returned invalid JSON: %s", exc)
            return self._fallback_extraction(doc)
        except Exception as exc:
            logger.error("OpenAI-compatible extraction error: %s", exc)
            return self._fallback_extraction(doc)

    def _parse_extraction(self, data: dict[str, Any], doc: ParsedDoc) -> ExtractionResult:
        pages = []
        for p in data.get("pages", []):
            raw_slug = p.get("slug", "")
            if not raw_slug:
                raw_slug = slugify(p.get("title", "untitled"))
            pages.append(
                WikiPage(
                    slug=raw_slug,
                    title=p.get("title", raw_slug.replace("-", " ").title()),
                    content=p.get("content", ""),
                    tags=p.get("tags", []),
                )
            )

        if not pages:
            # Fallback: generate a single page from the doc
            return self._fallback_extraction(doc)

        entities = [
            {"name": e.get("name", ""), "type": e.get("type", "concept")}
            for e in data.get("entities", [])
            if e.get("name")
        ]

        relationships = [
            {
                "from": r.get("from", ""),
                "to": r.get("to", ""),
                "type": r.get("type", "related_to"),
            }
            for r in data.get("relationships", [])
            if r.get("from") and r.get("to")
        ]

        return ExtractionResult(pages=pages, entities=entities, relationships=relationships)

    def _fallback_extraction(self, doc: ParsedDoc) -> ExtractionResult:
        """Generate a minimal page when the LLM call fails or produces no pages."""
        source = doc.source or "unknown"
        title = doc.metadata.get("title") or Path(source).stem.replace("-", " ").replace("_", " ").title()
        slug = slugify(title) or "untitled"

        # Trim content for the fallback page
        snippet = doc.text[:3000]
        content = (
            f"---\ntitle: {title}\ntags: [ingested]\nsource: {source}\n---\n\n"
            f"# {title}\n\n{snippet}"
        )
        return ExtractionResult(
            pages=[WikiPage(slug=slug, title=title, content=content, tags=["ingested"])],
            entities=[],
            relationships=[],
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_agent: WikiAgent | None = None


def get_agent(settings: Settings | None = None) -> WikiAgent:
    global _agent
    if _agent is None:
        _agent = WikiAgent(settings)
    return _agent


# Add Path import used in fallback
from pathlib import Path  # noqa: E402 — kept at module level for clarity
