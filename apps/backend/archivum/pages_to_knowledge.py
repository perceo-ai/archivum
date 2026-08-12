"""Project editable Markdown pages into the canonical knowledge store."""

from __future__ import annotations

import re

from archivum.ingest.agent import slugify
from archivum.knowledge.models import Citation, KnowledgeObject, KnowledgeRelationship
from archivum.knowledge.personal_root import ensure_personal_root, link_to_self
from archivum.knowledge.repository import KnowledgeRepository
from archivum.linting import WIKILINK_RE


_PROJECT_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n.*?^type:\s*project\s*$.*?^---\s*$",
    re.MULTILINE | re.DOTALL | re.IGNORECASE,
)


def _page_id(wiki_id: str, slug: str) -> str:
    return f"page:{wiki_id}:{slug}"


def _citation(source_id: str, quote: str, start: int | None = None) -> Citation:
    return Citation(
        source_id=source_id,
        chunk_id=source_id,
        span_start=start,
        span_end=start + len(quote) if start is not None else None,
        quote=quote,
    )


async def sync_page_to_knowledge(
    repo: KnowledgeRepository, *, slug: str, title: str, markdown: str, wiki_id: str
) -> None:
    """Upsert a user-authored page and its Markdown links into canonical knowledge."""
    page_id = _page_id(wiki_id, slug)
    scope = f"wiki:{wiki_id}"
    await repo.upsert_object(
        KnowledgeObject(
            id=page_id,
            kind="page",
            label=title,
            scope=scope,
            confidence=1.0,
            extraction_method="USER_AUTHORED",
            citations=[_citation(page_id, title)],
            properties={"slug": slug, "wiki_id": wiki_id},
        )
    )

    await ensure_personal_root(repo, wiki_id=wiki_id)
    relationship_type = "owns_project" if _PROJECT_FRONTMATTER_RE.search(markdown) else "authored_thought"
    await link_to_self(
        repo,
        page_id,
        relationship_type,
        citation=_citation(page_id, title),
    )

    for target in sorted({target.strip() for target in WIKILINK_RE.findall(markdown) if target.strip()}):
        target_slug = slugify(target)
        if not target_slug or target_slug == slug:
            continue
        target_id = _page_id(wiki_id, target_slug)
        start = markdown.find(f"[[{target}")
        await repo.upsert_relationship(
            KnowledgeRelationship(
                id=f"rel:{page_id}:references:{target_id}",
                src_id=page_id,
                dst_id=target_id,
                rel_type="references",
                scope=scope,
                confidence=1.0,
                extraction_method="USER_AUTHORED",
                citations=[_citation(page_id, target, start if start >= 0 else None)],
                properties={},
            )
        )
