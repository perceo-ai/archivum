from __future__ import annotations

import json
import re
import shutil
from typing import Any
from importlib.util import find_spec

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from archivum.auth import CurrentUser, require_owner
from archivum.config import Settings, get_settings
from archivum.db import graph, qdrant_client as qdrant, sqlite

router = APIRouter(prefix="/api", tags=["system"])


WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]")


def get_audio_feature_status() -> dict[str, Any]:
    whisper_available = find_spec("whisper") is not None
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_available = ffmpeg_path is not None
    missing = []
    if not whisper_available:
        missing.append("openai-whisper")
    if not ffmpeg_available:
        missing.append("ffmpeg")

    return {
        "available": whisper_available and ffmpeg_available,
        "dependencies": {
            "openai_whisper": whisper_available,
            "ffmpeg": ffmpeg_available,
        },
        "missing": missing,
        "commands": {
            "local": "cd backend && uv sync --extra audio",
            "ffmpeg": "Install ffmpeg with your OS package manager for video extraction.",
            "docker": "Use a derived audio-enabled image or rebuild the backend image with the audio extra and ffmpeg.",
        },
        "notes": [
            "The default published Docker images omit Whisper, Torch, and ffmpeg to keep installs smaller.",
            "Installing packages inside a running Docker container is not durable across upgrades.",
        ],
    }


@router.get("/audio-support")
async def audio_support(
    current_user: CurrentUser = Depends(require_owner),
) -> dict[str, Any]:
    return get_audio_feature_status()


@router.post("/rebuild-indexes")
async def rebuild_indexes(
    current_user: CurrentUser = Depends(require_owner),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pages = await sqlite.list_pages(current_user.wiki_id)

    # Re-init derived stores
    await qdrant.init_collection(settings)
    await graph.init_graph(settings)

    for p in pages:
        await qdrant.upsert_page(p["slug"], p["title"], p.get("content", ""), current_user.wiki_id, settings)
        await graph.upsert_page(p["slug"], p["title"], current_user.wiki_id)

        # Rebuild REFERENCES edges from wikilinks
        content = p.get("content", "") or ""
        for target in WIKILINK_RE.findall(content):
            target_slug = target.strip()
            if not target_slug:
                continue
            existing = await sqlite.get_page(target_slug, current_user.wiki_id)
            if existing:
                await graph.add_reference(p["slug"], target_slug, current_user.wiki_id)

    return {"detail": "Rebuilt indexes", "pages": len(pages)}


@router.get("/lint")
async def lint_wiki(
    current_user: CurrentUser = Depends(require_owner),
) -> dict[str, Any]:
    pages = await sqlite.list_pages(current_user.wiki_id)
    slug_set = {p["slug"] for p in pages}

    inbound: dict[str, int] = {s: 0 for s in slug_set}
    outbound: dict[str, int] = {s: 0 for s in slug_set}
    broken: list[dict[str, Any]] = []

    for p in pages:
        slug = p["slug"]
        content = p.get("content", "") or ""
        targets = [t.strip() for t in WIKILINK_RE.findall(content)]
        for t in targets:
            if not t:
                continue
            outbound[slug] = outbound.get(slug, 0) + 1
            if t in slug_set:
                inbound[t] = inbound.get(t, 0) + 1
            else:
                broken.append(
                    {
                        "type": "broken_wikilink",
                        "page": slug,
                        "target": t,
                        "suggestion": f"Create page '{t}' or fix link.",
                    }
                )

    orphan_pages = [
        {
            "type": "orphan_page",
            "page": s,
            "suggestion": "Add links to/from other pages so this page is discoverable.",
        }
        for s in slug_set
        if inbound.get(s, 0) == 0 and outbound.get(s, 0) == 0
    ]

    issues = broken + orphan_pages
    return {"issues": issues, "counts": {"issues": len(issues)}}


class LintFixRequest(BaseModel):
    type: str  # broken_wikilink | orphan
    source_slug: str | None = None
    link_target: str | None = None
    slug: str | None = None


@router.post("/lint/fix")
async def apply_lint_fix(
    body: LintFixRequest,
    current_user: CurrentUser = Depends(require_owner),
) -> dict[str, Any]:
    if body.type == "orphan":
        return {
            "detail": "no_auto_fix",
            "message": "Orphan pages cannot be auto-fixed; delete manually or add a wikilink to them.",
        }

    if body.type == "broken_wikilink":
        if not body.source_slug or not body.link_target:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="source_slug and link_target are required for broken_wikilink fixes",
            )

        page = await sqlite.get_page(body.source_slug, current_user.wiki_id)
        if not page:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Page '{body.source_slug}' not found",
            )

        content = page.get("content", "") or ""
        # Replace [[broken-link]] and [[broken-link|alias]] with plain text (the target slug)
        pattern = re.compile(
            r"\[\[" + re.escape(body.link_target) + r"(?:\|[^\]]+)?\]\]"
        )
        new_content = pattern.sub(body.link_target, content)

        if new_content == content:
            return {"detail": "no_change", "message": "Link not found in page content"}

        raw_tags = page.get("tags", "[]")
        if isinstance(raw_tags, list):
            tags: list[str] = raw_tags
        else:
            try:
                tags = json.loads(raw_tags)
            except Exception:
                tags = []

        await sqlite.upsert_page(
            slug=body.source_slug,
            title=page["title"],
            content=new_content,
            tags=tags,
            authored_by=page.get("authored_by", "agent"),
            wiki_id=current_user.wiki_id,
        )
        return {"detail": "fixed", "source_slug": body.source_slug, "link_target": body.link_target}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unknown fix type: {body.type}",
    )
