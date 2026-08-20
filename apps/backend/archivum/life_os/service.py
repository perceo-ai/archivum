"""Structured notes that Archivum knows how to start for you.

A daily note and a project note are just markdown pages with a known shape.
They used to be written twice — once as a page and once into a parallel set of
life_* tables — which meant two models of the same nouns that could disagree,
and only one of them showed up anywhere in the interface. The tables are gone;
these write pages through the one indexing path like everything else.
"""

from __future__ import annotations

from datetime import date

from archivum.config import Settings, get_settings
from archivum.db import sqlite
from archivum.indexing import reindex_page
from archivum.ingest.agent import slugify


def _frontmatter(kind: str, **fields: str) -> str:
    lines = [f"type: {kind}"]
    lines.extend(f"{key}: {value}" for key, value in fields.items() if value)
    rendered = "\n".join(lines)
    return f"---\n{rendered}\n---"


async def _write_page(
    slug: str,
    title: str,
    content: str,
    tags: list[str],
    wiki_id: str,
    settings: Settings | None = None,
) -> dict:
    # Take settings from the caller when offered: reaching for the global would
    # write into the deployment's vault path regardless of who asked.
    settings = settings or get_settings()
    path = settings.wiki_dir / f"{slug}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    await reindex_page(
        slug, wiki_id=wiki_id, settings=settings, force=True, reason="life-os"
    )
    row = await sqlite.get_page(slug, wiki_id)
    if row is None:
        raise RuntimeError(f"Page '{slug}' was not persisted")
    return row


async def ensure_daily_note(
    day: str | None = None,
    wiki_id: str = "default",
    settings: Settings | None = None,
) -> dict:
    """Today's note, created on first ask and returned untouched afterwards."""
    day = day or date.today().isoformat()
    slug = f"daily/{day}"

    existing = await sqlite.get_page(slug, wiki_id)
    if existing:
        return existing

    title = f"Daily note {day}"
    content = f"""{_frontmatter("daily", date=day)}

# {title}

## Log

## Tasks

## Decisions

## Links
"""
    return await _write_page(slug, title, content, ["daily"], wiki_id, settings)


async def register_project(
    key: str,
    name: str,
    summary: str = "",
    status: str = "active",
    wiki_id: str = "default",
    settings: Settings | None = None,
) -> dict:
    """Start a project note. The page is the project; there is no second record."""
    project_key = slugify(key)
    slug = f"projects/{project_key}"
    content = f"""{_frontmatter("project", project_key=project_key, status=status)}

# {name}

{summary}

## Outcomes

## Current work

## Decisions

## Tasks

## Links
"""
    return await _write_page(slug, name, content, ["project"], wiki_id, settings)
