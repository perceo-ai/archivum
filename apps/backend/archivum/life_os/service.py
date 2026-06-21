from __future__ import annotations

from datetime import date

from archivum.config import get_settings
from archivum.db import qdrant_client as qdrant
from archivum.db import sqlite
from archivum.ingest.agent import slugify


def _frontmatter(kind: str, **fields: str) -> str:
    lines = ["---", f"type: {kind}"]
    for key, value in fields.items():
        if value:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


async def ensure_daily_note(day: str | None = None, wiki_id: str = "default") -> dict:
    day = day or date.today().isoformat()
    slug = f"daily-{day}"
    existing = await sqlite.get_page(slug, wiki_id)
    if existing:
        return existing

    title = f"Daily Note {day}"
    content = f"""{_frontmatter("daily", date=day)}

# {title}

## Log

## Tasks

## Decisions

## Links
"""
    await sqlite.upsert_page(slug, title, content, ["daily"], "user", wiki_id)
    await qdrant.upsert_page(slug, title, content, wiki_id, get_settings())
    page = await sqlite.get_page(slug, wiki_id)
    if page is None:
        raise RuntimeError(f"Daily note was not created: {slug}")
    return page


async def register_project(
    key: str,
    name: str,
    summary: str = "",
    status: str = "active",
    wiki_id: str = "default",
) -> dict:
    project_key = slugify(key)
    slug = f"project-{project_key}"
    content = f"""{_frontmatter("project", project_key=project_key, status=status)}

# {name}

{summary}

## Outcomes

## Current Work

## Decisions

## Tasks

## Links
"""
    await sqlite.upsert_page(slug, name, content, ["project"], "user", wiki_id)
    await qdrant.upsert_page(slug, name, content, wiki_id, get_settings())
    return await sqlite.upsert_life_project(wiki_id, project_key, name, status, slug, summary)
